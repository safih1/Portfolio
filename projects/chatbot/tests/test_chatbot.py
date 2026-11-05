"""Tests for the chatbot Flask app (no network calls)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app  # noqa: E402
from groq_client import ChatServiceError  # noqa: E402


class FakeService:
    def stream(self, messages, system_prompt=None, temperature=0.7, max_tokens=1200):
        yield "Hello "
        yield "there!"

    def complete(self, messages, system_prompt=None, temperature=0.7, max_tokens=1200):
        return "Hello there!"

    def available_models(self):
        return ["openai/gpt-oss-120b"]


class BrokenService:
    def stream(self, *args, **kwargs):
        raise ChatServiceError("upstream failed")
        yield  # pragma: no cover


def make_client(service=None):
    app = create_app(service)
    app.config.update(TESTING=True)
    return app.test_client()


def test_index_renders():
    response = make_client(FakeService()).get("/")
    assert response.status_code == 200
    assert b"Groq Chat" in response.data


def test_health_reports_key(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    response = make_client(FakeService()).get("/api/health")
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["configured"] is True


def test_chat_requires_messages():
    response = make_client(FakeService()).post("/api/chat", json={})
    assert response.status_code == 400


def test_chat_non_stream():
    response = make_client(FakeService()).post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": "Hi"}], "stream": False},
    )
    assert response.status_code == 200
    assert response.get_json()["reply"] == "Hello there!"


def test_chat_streams_sse():
    response = make_client(FakeService()).post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": "Hi"}]},
    )
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert '"delta": "Hello "' in body
    assert "[DONE]" in body


def test_chat_surfaces_service_errors():
    response = make_client(BrokenService()).post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": "Hi"}]},
    )
    assert "upstream failed" in response.get_data(as_text=True)


def test_missing_key_returns_503(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    response = make_client(None).post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": "Hi"}]},
    )
    assert response.status_code == 503
    assert "GROQ_API_KEY" in response.get_json()["error"]
