"""Deterministic outreach templates used when no AI key is configured.

These are intentionally plain. They give the user a usable first draft without
pretending to have results or clients they do not have.
"""

from __future__ import annotations

from typing import Any

import config

SERVICES: dict[str, dict[str, str]] = {
    "AI receptionist / voice agent": {
        "short": "AI receptionist",
        "pain": "missed calls and slow follow-up",
        "promise": "an AI receptionist that answers every call, captures the details, and books appointments 24/7",
    },
    "n8n workflow automation": {
        "short": "workflow automation",
        "pain": "manual copying between tools",
        "promise": "workflows that move data between your tools automatically and remove the weekly admin",
    },
    "CRM setup and cleanup": {
        "short": "CRM setup",
        "pain": "leads living in spreadsheets and inboxes",
        "promise": "a simple CRM pipeline with automatic follow-ups so no lead gets forgotten",
    },
    "Landing page / website": {
        "short": "landing page",
        "pain": "a website that does not turn visitors into enquiries",
        "promise": "a focused landing page built to convert one clear audience into booked calls",
    },
    "AI chatbot": {
        "short": "AI chatbot",
        "pain": "repetitive questions and slow first replies",
        "promise": "a website chatbot trained on your business that answers common questions and captures leads",
    },
}

CHANNELS = ("email", "facebook_dm", "linkedin", "whatsapp", "follow_up")


def _first_name(lead: dict) -> str:
    name = (lead.get("name") or "").strip()
    if not name:
        return "there"
    return name.split()[0]


def _company(lead: dict) -> str:
    return (lead.get("company") or lead.get("name") or "your business").strip()


def _service(service: str) -> dict[str, str]:
    if service in SERVICES:
        return SERVICES[service]
    return {
        "short": service or "automation",
        "pain": "manual work and slow follow-up",
        "promise": "a simple automation that removes repetitive admin",
    }


def _cta() -> str:
    return config.CALENDLY_LINK or config.PORTFOLIO_URL or "reply and I'll send the details"


def build_message(
    lead: dict,
    channel: str = "email",
    service: str = "AI receptionist / voice agent",
    tone: str = "consultative",
    sender: dict[str, str] | None = None,
) -> dict[str, Any]:
    channel = channel if channel in CHANNELS else "email"
    info = _service(service)
    sender = sender or {}
    name = _first_name(lead)
    company = _company(lead)
    sender_name = sender.get("name") or config.SENDER_NAME or "Safi"
    sender_company = sender.get("company") or config.SENDER_COMPANY or "an AI automation studio"
    cta = _cta()

    proof = ""
    if sender.get("proof"):
        proof = f" {sender['proof']}"

    greeting = "Hi" if tone != "formal" else "Hello"
    signoff = "Best" if tone != "friendly" else "Cheers"

    if channel == "email":
        subject = f"Quick question about {company}"
        message = f"""{greeting} {name},

I had a look at {company} and noticed {info['pain']} is often the bottleneck for businesses like yours.

We build {info['promise']}.{proof}

Worth a 15-minute call to see whether it is a fit? {cta}

{signoff},
{sender_name}
{sender_company}"""
    elif channel == "facebook_dm":
        message = f"""{greeting} {name} — I came across {company} and had a quick question.

Is {info['pain']} something you are dealing with at the moment? We build {info['promise']}.

If it is useful, I can send a short example. Would that be okay?"""
    elif channel == "linkedin":
        message = f"""{greeting} {name}, I work with businesses like {company} on {info['short']}. The usual problem is {info['pain']}. We fix it with {info['promise']}. Open to a quick chat this week?"""
    elif channel == "whatsapp":
        message = f"""{greeting} {name}, quick one about {company}. Are you still handling {info['pain']} manually? We build {info['promise']}. Want me to send a 2-minute example?"""
    else:  # follow_up
        message = f"""{greeting} {name}, just bumping my note about {info['pain']} at {company}. If it is not a priority, no problem at all — happy to close the loop. If it is, {cta}."""

    return {
        "subject": subject if channel == "email" else "",
        "message": message,
        "why": f"Leads with the most common pain for {info['short']}: {info['pain']}.",
        "cta": cta,
        "channel": channel,
        "service": service,
        "tone": tone,
        "used_ai": False,
    }
