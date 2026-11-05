"""Groq chat service.

Keeps the API key server-side and exposes a small streaming interface that the
Flask layer can consume. No framework-specific code lives here so the service can
also be used from scripts or tests.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Sequence

from dotenv import load_dotenv
from groq import (
    APIConnectionError,
    APIStatusError,
    AuthenticationError,
    Groq,
    RateLimitError,
)

PROJECT_DIR = Path(__file__).resolve().parent
load_dotenv(PROJECT_DIR.parents[1] / ".env")
load_dotenv(PROJECT_DIR / ".env", override=False)

DEFAULT_MODEL = "openai/gpt-oss-120b"
DEFAULT_SYSTEM_PROMPT = (
    "You are a sharp, friendly AI assistant built by Safi. "
    "Give practical, specific answers. Use short paragraphs and clean markdown. "
    "If you are unsure, say so instead of inventing facts."
)

MAX_MESSAGES = 40
MAX_MESSAGE_CHARS = 12_000


class ChatConfigError(RuntimeError):
    """Raised when the service is not configured (for example a missing key)."""


class ChatServiceError(RuntimeError):
    """Raised when Groq cannot complete a request."""


def _clean_messages(messages: Sequence[dict]) -> list[dict]:
    """Validate and trim chat history coming from the browser."""
    cleaned: list[dict] = []
    for item in messages[-MAX_MESSAGES:]:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role not in {"user", "assistant"} or not isinstance(content, str):
            continue
        content = content.strip()
        if not content:
            continue
        cleaned.append({"role": role, "content": content[:MAX_MESSAGE_CHARS]})
    return cleaned


class ChatService:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        system_prompt: str | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("GROQ_API_KEY", "").strip()
        if not self.api_key:
            raise ChatConfigError(
                "GROQ_API_KEY is missing. Add it to .env (see .env.example)."
            )
        self.model = model or os.getenv("GROQ_MODEL", DEFAULT_MODEL)
        self.system_prompt = (
            system_prompt
            or os.getenv("CHATBOT_SYSTEM_PROMPT", "").strip()
            or DEFAULT_SYSTEM_PROMPT
        )
        self.client = Groq(api_key=self.api_key)

    def _payload(
        self,
        messages: Sequence[dict],
        system_prompt: str | None,
        temperature: float,
        max_tokens: int,
    ) -> dict:
        cleaned = _clean_messages(messages)
        if not cleaned:
            raise ValueError("At least one user message is required.")

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt or self.system_prompt},
                *cleaned,
            ],
            "temperature": max(0.0, min(2.0, float(temperature))),
            "max_tokens": max(64, min(8192, int(max_tokens))),
        }
        # gpt-oss models expose a reasoning trace. Low effort keeps replies snappy.
        if self.model.startswith("openai/gpt-oss"):
            payload["reasoning_effort"] = "low"
        return payload

    def stream(
        self,
        messages: Sequence[dict],
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1200,
    ) -> Iterable[str]:
        """Yield text deltas from Groq."""
        payload = self._payload(messages, system_prompt, temperature, max_tokens)
        try:
            stream = self.client.chat.completions.create(stream=True, **payload)
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                text = getattr(delta, "content", None)
                if text:
                    yield text
        except AuthenticationError as exc:
            raise ChatServiceError("Groq rejected the API key. Check GROQ_API_KEY.") from exc
        except RateLimitError as exc:
            raise ChatServiceError(
                "Groq rate limit reached. Wait a moment and try again."
            ) from exc
        except APIConnectionError as exc:
            raise ChatServiceError("Could not reach Groq. Check your connection.") from exc
        except APIStatusError as exc:
            message = getattr(exc, "message", None) or str(exc)
            raise ChatServiceError(f"Groq error: {message}") from exc

    def complete(
        self,
        messages: Sequence[dict],
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1200,
    ) -> str:
        return "".join(
            self.stream(
                messages,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        )

    def available_models(self) -> list[str]:
        try:
            return sorted(model.id for model in self.client.models.list().data)
        except Exception as exc:  # pragma: no cover - network dependent
            raise ChatServiceError(f"Could not list Groq models: {exc}") from exc
