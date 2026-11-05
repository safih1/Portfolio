# Django Client Portal

A small client workspace built with Django. It tracks clients, delivery projects, progress, and invoices without any build step or external services.

- Dashboard with active projects, outstanding balance, and paid revenue.
- Clients with contact details, project history, and billing totals.
- Projects with status, budget, dates, progress slider, and overdue detection.
- Invoices with generated numbers, filters, and one-click "mark paid".
- Django admin for every model, including a bulk mark-paid action.
- Demo data command and 29 tests.

## Requirements

- Python 3.10+
- Django 5.2

## Setup

From the repository root (after `pip install -r requirements.txt`):

```bash
cd projects/django-portal
python manage.py migrate
python manage.py seed_demo      # optional sample data
python manage.py runserver
```

Open <http://127.0.0.1:8000>. The admin is at <http://127.0.0.1:8000/admin/>.

Create an admin user:

```bash
python manage.py createsuperuser
```

The SQLite database lives at `data/portal.sqlite3` and is ignored by git.

## Routes

| URL | Purpose |
|---|---|
| `/` | Dashboard |
| `/clients/` | Client list with search |
| `/clients/new/` | Add a client |
| `/clients/<id>/` | Client detail, projects, invoices |
| `/projects/` | Project list with status filters |
| `/projects/new/` | Add a project (accepts `?client=<id>`) |
| `/projects/<id>/` | Project detail and progress update |
| `/invoices/` | Invoice list with status filters |
| `/invoices/new/` | Add an invoice (accepts `?project=<id>` or `?client=<id>`) |
| `/admin/` | Django admin |

## Models

**Client** — name, company, email (unique), phone, website, notes.

**Project** — client, name, status (`discovery`, `in_progress`, `review`, `delivered`, `on_hold`), budget, progress (0–100), start/due dates, description. `is_overdue` ignores delivered projects.

**Invoice** — client, optional project, number (unique), amount, status (`draft`, `sent`, `paid`, `overdue`), issue/due/paid dates, notes. Sent invoices past their due date display as overdue; drafts and paid invoices do not.

## Demo data

```bash
python manage.py seed_demo           # create or update the demo records
python manage.py seed_demo --reset   # clear portal records first
```

The command is idempotent: running it twice updates the same four clients, six projects, and six invoices instead of creating duplicates.

## Tests

```bash
cd projects/django-portal
python manage.py test
```

The suite covers models, dashboard totals, search, list filters, form prefill, validation, progress updates, invoice payments, admin pages, the bulk action, and the seed command.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `DJANGO_SECRET_KEY` | local development key | Session and CSRF signing |
| `DJANGO_DEBUG` | `1` | Set to `0` for production |
| `DJANGO_ALLOWED_HOSTS` | `127.0.0.1,localhost,testserver` | Comma-separated host list |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | empty | Comma-separated HTTPS origins for forms |

For production, set a real secret key, disable debug, configure `ALLOWED_HOSTS`, and add the public origin to `DJANGO_CSRF_TRUSTED_ORIGINS`. Static files are served by WhiteNoise, so no separate web server is needed.

## Deploy to Render

The repository root contains a `render.yaml` blueprint that builds this project from `projects/django-portal`.

1. Push the repository to GitHub.
2. In the Render dashboard, choose **New → Blueprint** and select the repository.
3. Apply the blueprint. Render installs dependencies, runs `collectstatic`, migrates, seeds the demo data, and starts Gunicorn.
4. Open the generated `https://<service>.onrender.com` URL.

The blueprint sets `DJANGO_DEBUG=0`, generates a secret key, allows `.onrender.com`, and trusts `https://*.onrender.com` for CSRF.

Free-tier notes:

- The instance sleeps after inactivity, so the first request may take a few seconds.
- The filesystem is ephemeral: SQLite data resets on deploy or restart. Use a Render disk or Postgres for persistent records.
- Create an admin user from the Render Shell with `python manage.py createsuperuser`.
- Demo data is reseeded on every build. Remove `python manage.py seed_demo` from `render.yaml` if you want an empty portal.

## Structure

```
django-portal/
├── config/              # Settings, URLs, WSGI/ASGI
├── portal/
│   ├── management/      # seed_demo command
│   ├── migrations/
│   ├── admin.py
│   ├── forms.py
│   ├── models.py
│   ├── tests.py
│   ├── urls.py
│   └── views.py
├── static/              # styles.css, app.js
├── templates/           # base layout, portal pages, 404
├── manage.py
└── requirements.txt
```
