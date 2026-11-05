# Lead Hunter

A local client-acquisition workspace: find businesses, audit their websites, qualify them with AI, write outreach, and track every follow-up.

It is built for solo freelancers and small agencies who need a simple CRM plus a repeatable prospecting workflow — not another bloated sales platform.

## What it does

- **Find leads** with the official Google Places API (category + city).
- **Pull Facebook Lead Ads** you own through the official Graph API, including a webhook for real-time leads.
- **Import CSV exports** from Facebook, LinkedIn, Apollo, spreadsheets, or any other source.
- **Audit websites** for email addresses, phone numbers, social profiles, live chat, booking tools, and tech stack.
- **Score leads 0–100** against your ideal customer profile with Groq.
- **Draft outreach** for email, Facebook Messenger, LinkedIn, WhatsApp, or a follow-up — in your voice, without invented case studies.
- **Analyze replies** and get a suggested next step.
- **Chat about a lead** in a compact Groq assistant inside the lead page — ask about fit, angles, or a first message.
- **Track everything** in SQLite: status, score, notes, drafts, audits, replies, and contact dates.
- **Export** any time to CSV.

## Compliance first

This project only uses official APIs and files you provide:

- No Facebook scraping, no logged-in automation, no unsolicited DM bots.
- No bypassing rate limits or platform protections.
- Website audits fetch public pages like a browser would. Respect `robots.txt`, terms of service, and local law.

When doing outreach, follow GDPR, CAN-SPAM, PECR, and the platform's terms. Keep proof of consent, include an opt-out path, and stop when someone asks you to.

## Quick start

```bash
cd projects/lead-hunter
python -m pip install -r requirements.txt

# Copy the root template and fill in what you need
copy ..\..\.env.example ..\..\.env

python cli.py init-db
python cli.py demo          # optional: 3 sample leads
python app.py               # http://127.0.0.1:5001
```

The app reads the root `.env`. Only `GROQ_API_KEY` is needed for AI features; everything else is optional.

## Configuration

Add these to the root `.env`:

| Variable | Required | Purpose |
|---|---|---|
| `GROQ_API_KEY` | For AI | Scoring, outreach drafts, reply analysis |
| `GROQ_MODEL` | No | Defaults to `openai/gpt-oss-120b` |
| `GOOGLE_PLACES_API_KEY` | For Google search | Places API (Text Search + Details) |
| `FACEBOOK_PAGE_ACCESS_TOKEN` | For Facebook | Page access token with `leads_retrieval` |
| `FACEBOOK_PAGE_ID` | For Facebook | Your Page ID |
| `FACEBOOK_APP_SECRET` | Recommended | Validates webhook signatures |
| `FACEBOOK_VERIFY_TOKEN` | For webhook | Any string you choose |
| `LEADHUNTER_DB` | No | SQLite path (default `projects/lead-hunter/data/leads.db`) |
| `FLASK_SECRET_KEY` | Production | Session signing key |
| `SENDER_NAME`, `SENDER_COMPANY` | No | Used in outreach copy |
| `CALENDLY_LINK`, `PORTFOLIO_URL` | No | Call to action in messages |

## How to use it

1. **Find or import** leads under *Find & import*.
2. **Open a lead** and run **Score with AI** to get a fit score and angle.
3. Use the **Lead assistant** panel to ask questions about the lead or get a first-message idea.
4. Run a **website audit** if you need an email or want to spot gaps (no chat, no booking, outdated stack).
5. Generate an **outreach draft**, edit it, send it yourself, then mark the lead as contacted.
6. Paste replies into the **reply analyzer** and follow the suggested next step.
7. Move the lead through `new → contacted → replied → qualified → won / lost`.
8. Export CSV whenever you need it.

## Facebook Lead Ads setup

1. Create an app at [developers.facebook.com](https://developers.facebook.com/apps/).
2. Add your Page and request `leads_retrieval` and `pages_read_engagement`.
3. Generate a Page access token and save it as `FACEBOOK_PAGE_ACCESS_TOKEN`.
4. Save the Page ID as `FACEBOOK_PAGE_ID`.
5. Copy a lead form ID from Meta Ads Manager and paste it into the tool, or run:

```bash
python cli.py facebook 1234567890 --limit 100
```

For real-time leads, expose the app over HTTPS (for example with `cloudflared tunnel` or `ngrok`) and set the webhook callback to:

```
https://your-domain/webhooks/facebook
```

Use the same `FACEBOOK_VERIFY_TOKEN`, set `FACEBOOK_APP_SECRET` so signatures are checked, and subscribe the Page to the `leadgen` field.

## Google Places setup

1. Create a Google Cloud project.
2. Enable **Places API** and create an API key.
3. Restrict the key to Places API and your IP where possible.
4. Save it as `GOOGLE_PLACES_API_KEY`.

```bash
python cli.py google "dentist" --location "Austin, TX" --limit 20
python cli.py google "roofing contractor" --location "Dallas, TX" --limit 10 --enrich
```

`--enrich` audits each website, which is slower but fills in emails and gaps.

## CSV import

Headers are detected case-insensitively. Common aliases are supported:

| Field | Examples |
|---|---|
| Name | `name`, `full_name`, `contact_name` |
| Company | `company`, `business_name`, `organization` |
| Email | `email`, `email_address`, `work_email` |
| Phone | `phone`, `mobile`, `telephone`, `whatsapp` |
| Website | `website`, `domain`, `url` |
| Location | `location`, `city`, `address`, `country` |
| Category | `category`, `industry`, `niche` |
| Notes | `notes`, `description`, `comments` |

Duplicates are merged by email, phone, website, or name + company.

```bash
python cli.py import leads.csv --platform linkedin
```

## CLI reference

```bash
python cli.py init-db
python cli.py stats
python cli.py demo
python cli.py import leads.csv
python cli.py google "dentist" --location "Austin, TX" --limit 20 --enrich
python cli.py facebook 1234567890 --limit 100
python cli.py forms
python cli.py audit https://example.com --save-lead 4
python cli.py score 4
python cli.py export leads.csv
python cli.py serve --port 5001
```

## Project layout

```
lead-hunter/
├── app.py                  # Flask routes and pages
├── cli.py                  # Command line tools
├── config.py               # Environment and paths
├── db.py                   # SQLite schema and queries
├── ai.py                   # Groq scoring, lead chat, outreach, reply analysis
├── providers/
│   ├── google_places.py    # Official Places API
│   ├── facebook.py         # Official Graph API + webhook helpers
│   ├── website.py          # Public page audit + email discovery
│   └── csv_import.py       # Flexible CSV parser
├── outreach/templates.py   # Deterministic fallback messages
├── templates/              # Jinja pages
├── static/                 # CSS and JS
├── data/                   # SQLite database (gitignored)
└── tests/                  # pytest suite
```

## Tests

```bash
cd projects/lead-hunter
python -m pytest tests -q
```

## Notes and limits

- This is a single-user local tool. It is not hardened for public multi-tenant deployment. If you host it, add authentication, CSRF protection, HTTPS, and a real secret key.
- SQLite is fine for tens of thousands of leads. Move to Postgres if you outgrow it.
- Groq drafts are suggestions. Read and edit every message before sending.
- Website audits are best-effort: JavaScript-rendered emails and contact forms may not appear.
- Facebook permissions and app review requirements change. Check Meta's current documentation.
