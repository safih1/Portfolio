# Portfolio + Client Acquisition Toolkit

Live portfolio: <https://portfolio-jade-nine-ctarhqtjpz.vercel.app>

This repository contains the static portfolio site at the root and the source code for the apps it showcases under `projects/`.

## Projects

| Project | What it does | Stack |
|---|---|---|
| [`projects/chatbot`](projects/chatbot) | Streaming Groq chat app with saved conversations, system prompt, and temperature controls | Flask, Groq, vanilla JS |
| [`projects/lead-hunter`](projects/lead-hunter) | Local CRM: find leads, audit websites, score fit, draft outreach, analyze replies, chat about a lead | Flask, Groq, SQLite |
| [`projects/django-portal`](projects/django-portal) | Client portal: projects, progress tracking, invoices, dashboard, and admin | Django, SQLite |
| [`projects/n8n-workflows`](projects/n8n-workflows) | Importable n8n automation workflows | n8n JSON |

The portfolio cards link to each project's source and setup guide. The Flask apps are designed to run locally; the Django portal has a Render blueprint for a public demo.

## Run locally

```bash
git clone https://github.com/safih1/Portfolio.git
cd Portfolio

python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env   # macOS/Linux: cp .env.example .env
```

Add at least `GROQ_API_KEY` to `.env` for the chatbot and Lead Hunter.

### Chatbot

```bash
cd projects/chatbot
python app.py
```

Open <http://127.0.0.1:5000>.

### Lead Hunter

```bash
cd projects/lead-hunter
python cli.py init-db
python cli.py demo
python app.py
```

Open <http://127.0.0.1:5001>.

### Django Client Portal

```bash
cd projects/django-portal
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Open <http://127.0.0.1:8000>. Create an admin user with `python manage.py createsuperuser`.

### n8n workflows

Import the JSON files from `projects/n8n-workflows` into n8n: **Workflows → Import from file**, add credentials, review the trigger, then activate.

## Deploy

**Portfolio:** Vercel serves the repository root as a static site. There is no build step. Push to `main` and Vercel redeploys automatically.

**Django portal:** the root [`render.yaml`](render.yaml) blueprint deploys `projects/django-portal` with Gunicorn and WhiteNoise.

1. In Render, choose **New → Blueprint**.
2. Select this repository.
3. Apply the blueprint and wait for the build.
4. Open the generated `https://<service>.onrender.com` URL.

Render runs migrations and seeds the demo data on each build. The free tier sleeps after inactivity and uses an ephemeral filesystem, so SQLite records reset on deploy or restart. Use a Render disk or Postgres for persistent data. See the [portal README](projects/django-portal/README.md#deploy-to-render).

**Flask apps:** intended for local use. Add authentication, a production WSGI server, and rate limits before exposing them publicly.

## Tests

```bash
cd projects/chatbot && python -m pytest tests -q
cd projects/lead-hunter && python -m pytest tests -q
cd projects/django-portal && python manage.py test
```

## Layout

```text
.
├── index.html, portfolio.html, styles.css, script.js   # Live portfolio
├── portfolio.pdf, og-image.png, PORTFOLIO.md
├── projects/
│   ├── chatbot/              # Groq streaming chat app
│   ├── lead-hunter/          # Local CRM + prospecting tools
│   ├── django-portal/        # Django client portal
│   └── n8n-workflows/        # Importable automation workflows
├── render.yaml               # Render blueprint for Django
├── requirements.txt
├── .env.example
└── README.md
```

## Security

- Never commit `.env`, API keys, tokens, or local databases.
- Keep the Flask apps on `127.0.0.1` unless you add authentication.
- Use official APIs and follow each platform's terms.

## License

MIT
