"""Command line interface for Lead Hunter.

Examples:
    python cli.py init-db
    python cli.py demo
    python cli.py import leads.csv --platform csv
    python cli.py google "dentist" --location "Austin, TX" --limit 20 --enrich
    python cli.py facebook 1234567890 --limit 100
    python cli.py score 4
    python cli.py export leads.csv
"""

from __future__ import annotations

import argparse
import json
import sys

import ai
import db
from providers import csv_import, facebook, google_places, website


def _print(value) -> None:
    if isinstance(value, (dict, list)):
        print(json.dumps(value, indent=2, ensure_ascii=False, default=str))
    else:
        print(value)


def cmd_init_db(_args) -> int:
    db.init_db()
    print(f"Database ready: {db.get_db_path()}")
    return 0


def cmd_stats(_args) -> int:
    _print(db.stats())
    return 0


def cmd_demo(_args) -> int:
    _print(db.seed_demo())
    return 0


def cmd_import(args) -> int:
    parsed = csv_import.parse_csv(args.file)
    leads = parsed["leads"]
    if args.platform:
        for lead in leads:
            lead["platform"] = args.platform
    result = db.bulk_upsert(leads)
    result["mapping"] = parsed["mapping"]
    _print(result)
    return 0


def cmd_google(args) -> int:
    leads = google_places.search_places(
        args.query,
        args.location,
        limit=args.limit,
        with_details=True,
        enrich=args.enrich,
    )
    _print(db.bulk_upsert(leads))
    return 0


def cmd_facebook(args) -> int:
    client = facebook.FacebookClient()
    leads = client.fetch_form_leads(args.form_id, limit=args.limit)
    _print(db.bulk_upsert(leads))
    return 0


def cmd_forms(_args) -> int:
    _print(facebook.FacebookClient().list_forms())
    return 0


def cmd_audit(args) -> int:
    audit = website.audit_website(args.url, deep=True)
    if args.save_lead:
        lead = db.get_lead(args.save_lead)
        if not lead:
            print(f"Lead {args.save_lead} not found.", file=sys.stderr)
            return 1
        updates = {}
        if audit["emails"] and not lead.get("email"):
            updates["email"] = audit["emails"][0]
        if audit["phones"] and not lead.get("phone"):
            updates["phone"] = audit["phones"][0]
        if updates:
            db.update_lead(args.save_lead, **updates)
        db.add_activity(args.save_lead, "website_audit", json.dumps(audit, indent=2), "website")
    _print(audit)
    return 0


def cmd_score(args) -> int:
    lead = db.get_lead(args.lead_id)
    if not lead:
        print(f"Lead {args.lead_id} not found.", file=sys.stderr)
        return 1
    result = ai.score_lead(lead)
    db.update_lead(
        args.lead_id,
        score=result["score"],
        score_reason=result["reason"],
        angle=result["angle"],
    )
    db.add_activity(args.lead_id, "ai_score", json.dumps(result, indent=2), "groq")
    _print(result)
    return 0


def cmd_export(args) -> int:
    rows = db.list_leads(limit=100000)
    text = db.export_rows(rows)
    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        print(f"Exported {len(rows)} leads to {args.output}")
    else:
        print(text)
    return 0


def cmd_serve(args) -> int:
    from app import app

    app.run(host=args.host, port=args.port, debug=args.debug)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Lead Hunter CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="Create the SQLite database").set_defaults(func=cmd_init_db)
    sub.add_parser("stats", help="Show pipeline statistics").set_defaults(func=cmd_stats)
    sub.add_parser("demo", help="Load three demo leads").set_defaults(func=cmd_demo)
    sub.add_parser("forms", help="List Facebook lead forms for the configured Page").set_defaults(func=cmd_forms)

    import_parser = sub.add_parser("import", help="Import a CSV file")
    import_parser.add_argument("file")
    import_parser.add_argument("--platform", help="Override the platform for every row")
    import_parser.set_defaults(func=cmd_import)

    google_parser = sub.add_parser("google", help="Search Google Places")
    google_parser.add_argument("query")
    google_parser.add_argument("--location", default="")
    google_parser.add_argument("--limit", type=int, default=20)
    google_parser.add_argument("--enrich", action="store_true", help="Audit each website")
    google_parser.set_defaults(func=cmd_google)

    facebook_parser = sub.add_parser("facebook", help="Pull leads from a Facebook lead form")
    facebook_parser.add_argument("form_id")
    facebook_parser.add_argument("--limit", type=int, default=100)
    facebook_parser.set_defaults(func=cmd_facebook)

    audit_parser = sub.add_parser("audit", help="Audit a website")
    audit_parser.add_argument("url")
    audit_parser.add_argument("--save-lead", type=int, help="Save findings to this lead ID")
    audit_parser.set_defaults(func=cmd_audit)

    score_parser = sub.add_parser("score", help="Score a lead with Groq")
    score_parser.add_argument("lead_id", type=int)
    score_parser.set_defaults(func=cmd_score)

    export_parser = sub.add_parser("export", help="Export leads as CSV")
    export_parser.add_argument("output", nargs="?")
    export_parser.set_defaults(func=cmd_export)

    serve_parser = sub.add_parser("serve", help="Run the web app")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=5001)
    serve_parser.add_argument("--debug", action="store_true")
    serve_parser.set_defaults(func=cmd_serve)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except (ai.AIConfigError, ai.AIError, google_places.GooglePlacesError,
            facebook.FacebookError, website.WebsiteError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
