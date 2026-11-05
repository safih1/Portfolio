"""Flask web app for the Groq-powered chatbot."""

from __future__ import annotations

import json
import os
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request, stream_with_context

from groq_client import ChatConfigError, ChatService, ChatServiceError

PROJECT_DIR = Path(__file__).resolve().parent
REPO_ROOT = PROJECT_DIR.parents[1]
load_dotenv(REPO_ROOT / ".env")
load_dotenv(PROJECT_DIR / ".env", override=False)


class SlidingWindowLimiter:
    """Tiny in-process rate limiter (good enough for a single-user tool)."""

    def __init__(self, max_requests: int = 20, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            bucket = self._hits[key]
            while bucket and now - bucket[0] > self.window_seconds:
                bucket.popleft()
            if len(bucket) >= self.max_requests:
                return False
            bucket.append(now)
            return True


def create_app(service: ChatService | None = None) -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024
    app.config["CHAT_SERVICE"] = service
    limiter = SlidingWindowLimiter(
        max_requests=int(os.getenv("CHAT_RATE_LIMIT", "20")),
        window_seconds=int(os.getenv("CHAT_RATE_WINDOW", "60")),
    )

    def get_service() -> ChatService:
        existing = app.config.get("CHAT_SERVICE")
        if existing is not None:
            return existing
        return ChatService()

    @app.after_request
    def security_headers(response: Response) -> Response:
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response

    @app.get("/")
    def index() -> str:
        return render_template("index.html")

    @app.get("/api/health")
    def health():
        configured = bool(os.getenv("GROQ_API_KEY", "").strip())
        return jsonify(
            {
                "status": "ok" if configured else "missing_key",
                "configured": configured,
                "model": os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
            }
        )

    @app.get("/api/models")
    def models():
        try:
            return jsonify({"models": get_service().available_models()})
        except ChatConfigError as exc:
            return jsonify({"error": str(exc)}), 503

    @app.post("/api/chat")
    def chat():
        if not limiter.allow(request.remote_addr or "local"):
            return jsonify({"error": "Too many requests. Please slow down."}), 429

        data = request.get_json(silent=True) or {}
        messages = data.get("messages")
        if not isinstance(messages, list) or not messages:
            return jsonify({"error": "Send a non-empty 'messages' array."}), 400

        temperature = data.get("temperature", 0.7)
        max_tokens = data.get("max_tokens", 1200)
        system_prompt = data.get("system_prompt") or None
        use_stream = data.get("stream", True)

        try:
            service = get_service()
        except ChatConfigError as exc:
            return jsonify({"error": str(exc)}), 503

        if not use_stream:
            try:
                reply = service.complete(
                    messages,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return jsonify({"reply": reply})
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
            except ChatServiceError as exc:
                return jsonify({"error": str(exc)}), 502

        @stream_with_context
        def generate():
            try:
                for delta in service.stream(
                    messages,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ):
                    yield f"data: {json.dumps({'delta': delta})}\n\n"
            except (ChatServiceError, ValueError) as exc:
                yield f"data: {json.dumps({'error': str(exc)})}\n\n"
            finally:
                yield "data: [DONE]\n\n"

        return Response(
            generate(),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
            },
        )

    @app.errorhandler(413)
    def too_large(_error):
        return jsonify({"error": "Request is too large."}), 413

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    print(f"Chatbot running at http://127.0.0.1:{port}")
    app.run(host=os.getenv("HOST", "127.0.0.1"), port=port, debug=debug)
