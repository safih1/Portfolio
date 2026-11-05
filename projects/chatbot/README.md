# Groq Chat

A clean, streaming AI chat app powered by [Groq](https://groq.com). The API key stays on the server; conversations stay in the browser.

![Groq Chat](https://img.shields.io/badge/model-openai%2Fgpt--oss--120b-35d39a)

## Features

- **Real streaming** over Server-Sent Events — text appears as it is generated.
- **Local history** in `localStorage` with multiple conversations, export, and delete.
- **Editable system prompt** and temperature.
- **Safe markdown** rendering (code blocks, lists, links, bold, italic, quotes) with HTML escaped first.
- **Rate limiting** per IP, request-size limits, and security headers.
- **No build step.** Flask + vanilla HTML/CSS/JS.
- **Model picker ready.** Change `GROQ_MODEL` in `.env` at any time.

## Quick start

```bash
cd projects/chatbot
python -m pip install -r requirements.txt

# From the repo root, copy the template and add your key
copy ..\..\.env.example ..\..\.env
# GROQ_API_KEY=gsk_...

python app.py
```

Open <http://127.0.0.1:5000>.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `GROQ_API_KEY` | — | Required. Get one at [console.groq.com](https://console.groq.com/keys) |
| `GROQ_MODEL` | `openai/gpt-oss-120b` | Any chat model available on your Groq account |
| `CHATBOT_SYSTEM_PROMPT` | Built-in assistant prompt | Override the default system prompt |
| `CHAT_RATE_LIMIT` | `20` | Requests allowed per window |
| `CHAT_RATE_WINDOW` | `60` | Window in seconds |
| `HOST` | `127.0.0.1` | Bind address |
| `PORT` | `5000` | Port |
| `FLASK_DEBUG` | `0` | Set to `1` for local development only |

Check which models your key can use:

```bash
python -c "from groq import Groq; import os; print([m.id for m in Groq(api_key=os.environ['GROQ_API_KEY']).models.list().data])"
```

## API

### `GET /api/health`

```json
{ "status": "ok", "configured": true, "model": "openai/gpt-oss-120b" }
```

### `POST /api/chat`

Request:

```json
{
  "messages": [{ "role": "user", "content": "Hello" }],
  "temperature": 0.7,
  "stream": true
}
```

Streaming response (`text/event-stream`):

```
data: {"delta": "Hello"}
data: {"delta": " there"}
data: [DONE]
```

Set `"stream": false` to receive `{ "reply": "..." }` instead.

### `GET /api/models`

Returns the model IDs available to the configured key.

## Project layout

```
chatbot/
├── app.py                # Flask app, routes, rate limiting, SSE
├── groq_client.py        # Groq wrapper and prompt handling
├── templates/index.html  # UI
├── static/styles.css     # Theme
├── static/app.js         # Streaming client, history, markdown
├── tests/                # pytest suite (mocked, no network)
└── requirements.txt
```

## Tests

```bash
cd projects/chatbot
python -m pytest tests -q
```

## Deploying

Any host that runs Python works (Render, Railway, Fly.io, a VPS). For production:

- Set `FLASK_DEBUG=0` and a real `HOST`/`PORT`.
- Put it behind HTTPS and a reverse proxy.
- Use a production WSGI server, for example:

```bash
pip install gunicorn
gunicorn -w 2 -k gthread --threads 8 -b 0.0.0.0:5000 app:app
```

- Add authentication if it is public — this app has no user accounts.
- Keep `.env` out of git.

## Notes

- The in-memory rate limiter resets when the process restarts. Use Redis if you run multiple workers.
- Conversation history is sent from the browser on each request. The server keeps no database.
- Groq bills per token. `max_tokens` is capped at 8192 per request.
