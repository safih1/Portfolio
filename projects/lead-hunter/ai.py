"""Groq-powered lead scoring and outreach drafting."""

from __future__ import annotations

import json
import re
from typing import Any

from groq import APIConnectionError, APIStatusError, AuthenticationError, Groq, RateLimitError

import config

DEFAULT_ICP = (
    "Local and small-to-mid B2B service businesses (dental, medical, real estate, "
    "home services, clinics, agencies) that rely on phone calls or Facebook lead ads, "
    "run on spreadsheets/manual follow-up, and have no automation or CRM in place."
)


class AIConfigError(RuntimeError):
    pass


class AIError(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(config.GROQ_API_KEY)


def _client() -> Groq:
    if not config.GROQ_API_KEY:
        raise AIConfigError("GROQ_API_KEY is missing. Add it to .env.")
    return Groq(api_key=config.GROQ_API_KEY)


def _reasoning_kwargs() -> dict:
    if config.GROQ_MODEL.startswith("openai/gpt-oss"):
        return {"reasoning_effort": "low"}
    return {}


def _chat(
    messages: list[dict],
    *,
    temperature: float = 0.4,
    max_tokens: int = 1400,
    json_mode: bool = False,
) -> str:
    kwargs: dict[str, Any] = {
        "model": config.GROQ_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        **_reasoning_kwargs(),
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    try:
        response = _client().chat.completions.create(**kwargs)
    except AuthenticationError as exc:
        raise AIError("Groq rejected the API key. Check GROQ_API_KEY.") from exc
    except RateLimitError as exc:
        raise AIError("Groq rate limit reached. Try again in a moment.") from exc
    except APIConnectionError as exc:
        raise AIError("Could not reach Groq. Check your connection.") from exc
    except APIStatusError as exc:
        raise AIError(f"Groq error: {getattr(exc, 'message', str(exc))}") from exc

    content = response.choices[0].message.content if response.choices else ""
    if not content:
        raise AIError("Groq returned an empty response. Try again.")
    return content


def parse_json(text: str) -> dict:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                value = json.loads(text[start : end + 1])
                return value if isinstance(value, dict) else {}
            except json.JSONDecodeError:
                pass
    raise AIError("Could not parse the AI response as JSON.")


def _lead_brief(lead: dict) -> str:
    return "\n".join(
        [
            f"Name: {lead.get('name', '')}",
            f"Company: {lead.get('company', '')}",
            f"Email: {lead.get('email', '')}",
            f"Phone: {lead.get('phone', '')}",
            f"Website: {lead.get('website', '')}",
            f"Platform/source: {lead.get('platform', '')}",
            f"Location: {lead.get('location', '')}",
            f"Category: {lead.get('category', '')}",
            f"Notes: {lead.get('notes', '')}",
        ]
    )


def score_lead(lead: dict, icp: str | None = None) -> dict:
    icp = icp or DEFAULT_ICP
    system = (
        "You qualify inbound and outbound leads for an AI automation agency. "
        "Be skeptical and concrete. Return only valid JSON."
    )
    user = f"""Ideal customer profile:
{icp}

Lead:
{_lead_brief(lead)}

Score this lead from 0-100 for likelihood to buy AI automation services soon.
Return JSON with exactly these keys:
- "score": integer 0-100
- "tier": "hot" | "warm" | "cold"
- "reason": one or two sentences explaining the score using specific evidence
- "angle": one concrete outreach angle (the pain to lead with), max 25 words
- "next_action": the single best next step
- "signals": array of up to 4 short strings (positive or negative signals)

Do not invent facts that are not in the lead data."""
    data = parse_json(_chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.2,
        json_mode=True,
    ))
    try:
        score = max(0, min(100, int(data.get("score", 0))))
    except (TypeError, ValueError):
        score = 0
    tier = str(data.get("tier", "")).lower()
    if tier not in {"hot", "warm", "cold"}:
        tier = "hot" if score >= 70 else "warm" if score >= 40 else "cold"
    signals = data.get("signals") if isinstance(data.get("signals"), list) else []
    return {
        "score": score,
        "tier": tier,
        "reason": str(data.get("reason", "")).strip(),
        "angle": str(data.get("angle", "")).strip(),
        "next_action": str(data.get("next_action", "")).strip(),
        "signals": [str(item)[:160] for item in signals[:4]],
    }


CHANNEL_RULES = {
    "email": "Write a cold email. Include a subject line under 60 characters. Body under 130 words, plain text, one clear call to action. No fake case studies.",
    "facebook_dm": "Write a Facebook Messenger message. Under 75 words, conversational, no subject, no hard pitch. Reference the business specifically. One question at the end.",
    "linkedin": "Write a LinkedIn message. Under 90 words, professional but human, no subject. If this is a connection request, keep it under 280 characters.",
    "whatsapp": "Write a WhatsApp message. Under 55 words, friendly and direct, no links unless the CTA link is short.",
    "follow_up": "Write a short follow-up bump. Under 60 words. Reference the previous message without guilt-tripping. Make it easy to say no.",
}


def generate_outreach(
    lead: dict,
    channel: str = "email",
    service: str = "AI receptionist / voice agent",
    tone: str = "consultative",
) -> dict:
    channel = channel if channel in CHANNEL_RULES else "email"
    sender = config.SENDER_NAME or "the sender"
    company = config.SENDER_COMPANY or "an AI automation studio"
    cta = config.CALENDLY_LINK or config.PORTFOLIO_URL or "reply to this message"

    system = (
        "You write short, specific, non-spammy B2B outreach for a small AI automation "
        "studio. You never invent results, clients, or metrics. You sound like a busy "
        "human, not a marketer. Return only valid JSON."
    )
    user = f"""Write one outreach message.

Channel rules: {CHANNEL_RULES[channel]}
Tone: {tone}
Service being offered: {service}
Sender: {sender} at {company}
CTA: {cta}

Lead:
{_lead_brief(lead)}

Return JSON with exactly these keys:
- "subject": subject line, or empty string for DM channels
- "message": the message body, ready to send
- "why": one sentence on why this angle fits this lead
- "cta": the call to action used

Hard rules:
- No fabricated proof, case studies, or numbers.
- No "I hope this finds you well", "revolutionary", "game-changer", or emoji spam.
- Personalize using only the lead data above.
- Keep the message natural and easy to reply to."""
    data = parse_json(_chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.65,
        json_mode=True,
    ))
    message = str(data.get("message", "")).strip()
    if not message:
        raise AIError("The AI returned an empty message. Try again.")
    subject = str(data.get("subject", "")).strip()
    if channel != "email":
        subject = ""
    return {
        "subject": subject,
        "message": message,
        "why": str(data.get("why", "")).strip(),
        "cta": str(data.get("cta", "")).strip(),
        "channel": channel,
        "service": service,
        "tone": tone,
    }


MAX_CHAT_MESSAGES = 20
MAX_CHAT_CHARS = 4000


def chat_about_lead(lead: dict, messages: list[dict]) -> str:
    """Answer questions about one lead in a compact chat assistant."""
    history: list[dict] = []
    for item in messages:
        if not isinstance(item, dict):
            raise AIError("Each message must be an object with role and content.")
        role = str(item.get("role", "")).strip()
        content = str(item.get("content", "")).strip()
        if role not in {"user", "assistant"}:
            raise AIError("Message role must be user or assistant.")
        if not content:
            raise AIError("Message content cannot be empty.")
        history.append({"role": role, "content": content[:MAX_CHAT_CHARS]})
    if not history:
        raise AIError("Send a question first.")
    if history[-1]["role"] != "user":
        raise AIError("The last message must be a question from the user.")
    history = history[-MAX_CHAT_MESSAGES:]
    if history[0]["role"] == "assistant":
        history = history[1:]

    context = [_lead_brief(lead)]
    if lead.get("status"):
        context.append(f"Status: {lead['status']}")
    if lead.get("score") is not None:
        context.append(f"Score: {lead['score']}/100")
    if lead.get("score_reason"):
        context.append(f"Score reason: {lead['score_reason']}")
    if lead.get("angle"):
        context.append(f"Suggested angle: {lead['angle']}")

    system = (
        "You are the lead assistant inside a small AI automation agency's CRM. "
        "Answer questions about this specific lead using only the lead record and "
        "the conversation. Be concise, practical, and honest. If the answer is not "
        "in the record, say what is missing instead of inventing it. Never invent "
        "clients, results, or metrics. Plain text only, no markdown headings.\n\n"
        "Lead record:\n" + "\n".join(context)
    )
    return _chat(
        [{"role": "system", "content": system}, *history],
        temperature=0.4,
        max_tokens=700,
    ).strip()


def summarize_reply(lead: dict, reply_text: str) -> dict:
    system = (
        "You analyze sales replies for a small AI automation studio. Be concise and "
        "practical. Return only valid JSON."
    )
    user = f"""Lead:
{_lead_brief(lead)}

Their reply:
{reply_text}

Return JSON with exactly these keys:
- "summary": one or two sentences
- "intent": one of "interested", "not_interested", "question", "objection", "later", "unclear"
- "next_step": the single best next action
- "suggested_reply": a short reply the sender can edit and send
Do not invent commitments or facts."""
    data = parse_json(_chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.3,
        json_mode=True,
    ))
    return {
        "summary": str(data.get("summary", "")).strip(),
        "intent": str(data.get("intent", "unclear")).lower(),
        "next_step": str(data.get("next_step", "")).strip(),
        "suggested_reply": str(data.get("suggested_reply", "")).strip(),
    }
