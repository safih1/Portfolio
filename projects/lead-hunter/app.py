"""Lead Hunter — a small CRM and client-acquisition workspace.

Run:
    python app.py
"""

from __future__ import annotations

import csv
import io
import json
import math
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

from flask import (
    Flask,
    Response,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

import ai
import config
import db
from outreach import templates as outreach_templates
from providers import csv_import, facebook, google_places, website

CHANNELS = ["email", "facebook_dm", "linkedin", "whatsapp", "follow_up"]
TONES = ["consultative", "direct", "friendly", "formal"]
PER_PAGE = 25


def _int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def create_app(db_path: str | Path | None = None) -> Flask:
    if db_path is not None:
        db.set_db_path(db_path)
    db.init_db()

    app = Flask(__name__)
    app.secret_key = config.env("FLASK_SECRET_KEY") or secrets.token_hex(24)
    app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

    @app.template_filter("timeago")
    def timeago(value: str) -> str:
        if not value:
            return "—"
        try:
            moment = datetime.fromisoformat(value)
        except ValueError:
            return value
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        seconds = max(0, int((datetime.now(timezone.utc) - moment).total_seconds()))
        if seconds < 60:
            return "just now"
        if seconds < 3600:
            return f"{seconds // 60}m ago"
        if seconds < 86400:
            return f"{seconds // 3600}h ago"
        return f"{seconds // 86400}d ago"

    @app.template_filter("initials")
    def initials(value: str) -> str:
        parts = [part for part in (value or "").split() if part]
        return "".join(part[0].upper() for part in parts[:2]) or "?"

    @app.template_filter("score_class")
    def score_class(value) -> str:
        try:
            score = int(value)
        except (TypeError, ValueError):
            return "cold"
        return "hot" if score >= 70 else "warm" if score >= 40 else "cold"

    def render_lead(lead_id: int, **extra):
        lead = db.get_lead(lead_id)
        if not lead:
            abort(404)
        context = {
            "lead": lead,
            "activities": db.list_activities(lead_id),
            "services": config.DEFAULT_SERVICES,
            "channels": CHANNELS,
            "tones": TONES,
            "ai_ready": ai.is_configured(),
            "google_ready": bool(config.GOOGLE_PLACES_API_KEY),
            "facebook_ready": bool(config.FACEBOOK_PAGE_ACCESS_TOKEN),
        }
        context.update(extra)
        return render_template("lead_detail.html", **context)

    # ---------- Dashboard ----------
    @app.get("/")
    def dashboard():
        stats = db.stats()
        return render_template(
            "dashboard.html",
            stats=stats,
            hot_leads=db.list_leads(min_score=70, limit=6),
            recent=db.list_leads(limit=10),
            followups=db.list_leads(status="contacted", limit=6),
            ai_ready=ai.is_configured(),
            google_ready=bool(config.GOOGLE_PLACES_API_KEY),
            facebook_ready=bool(config.FACEBOOK_PAGE_ACCESS_TOKEN),
        )

    # ---------- Leads ----------
    @app.get("/leads")
    def leads():
        query = (request.args.get("q") or "").strip()
        status = (request.args.get("status") or "").strip()
        platform = (request.args.get("platform") or "").strip()
        page = max(1, _int(request.args.get("page"), 1))
        total = db.count_leads(query=query, status=status, platform=platform)
        pages = max(1, math.ceil(total / PER_PAGE))
        rows = db.list_leads(
            query=query,
            status=status,
            platform=platform,
            limit=PER_PAGE,
            offset=(page - 1) * PER_PAGE,
        )
        return render_template(
            "leads.html",
            leads=rows,
            total=total,
            page=page,
            pages=pages,
            query=query,
            status=status,
            platform=platform,
            statuses=db.STATUSES,
            platforms=[row["platform"] for row in db.stats()["by_platform"]],
        )

    @app.post("/leads/new")
    def lead_create():
        payload = {
            "name": request.form.get("name"),
            "company": request.form.get("company"),
            "email": request.form.get("email"),
            "phone": request.form.get("phone"),
            "website": request.form.get("website"),
            "platform": request.form.get("platform") or "manual",
            "profile_url": request.form.get("profile_url"),
            "location": request.form.get("location"),
            "category": request.form.get("category"),
            "notes": request.form.get("notes"),
        }
        if not any(payload.get(field) for field in ("name", "email", "phone", "company")):
            flash("Add at least a name, company, email, or phone.", "error")
            return redirect(url_for("leads"))
        lead_id, created = db.upsert_lead(payload)
        flash("Lead added." if created else "Existing lead updated.", "success")
        return redirect(url_for("lead_detail", lead_id=lead_id))

    @app.get("/leads/<int:lead_id>")
    def lead_detail(lead_id: int):
        return render_lead(lead_id)

    @app.post("/leads/<int:lead_id>/update")
    def lead_update(lead_id: int):
        if not db.get_lead(lead_id):
            abort(404)
        fields = {}
        for field in (
            "name",
            "company",
            "email",
            "phone",
            "website",
            "platform",
            "profile_url",
            "location",
            "category",
            "notes",
            "status",
            "score",
        ):
            if field in request.form:
                fields[field] = request.form.get(field)
        if fields.get("status") and fields["status"] not in db.STATUSES:
            flash("Invalid status.", "error")
            return redirect(url_for("lead_detail", lead_id=lead_id))
        db.update_lead(lead_id, **fields)
        flash("Lead updated.", "success")
        return redirect(url_for("lead_detail", lead_id=lead_id))

    @app.post("/leads/<int:lead_id>/delete")
    def lead_delete(lead_id: int):
        db.delete_lead(lead_id)
        flash("Lead deleted.", "success")
        return redirect(url_for("leads"))

    @app.post("/leads/<int:lead_id>/score")
    def lead_score(lead_id: int):
        lead = db.get_lead(lead_id)
        if not lead:
            abort(404)
        try:
            result = ai.score_lead(lead)
        except ai.AIConfigError as exc:
            flash(str(exc), "error")
            return redirect(url_for("lead_detail", lead_id=lead_id))
        except ai.AIError as exc:
            flash(f"Scoring failed: {exc}", "error")
            return redirect(url_for("lead_detail", lead_id=lead_id))

        db.update_lead(
            lead_id,
            score=result["score"],
            score_reason=result["reason"],
            angle=result["angle"],
        )
        db.add_activity(
            lead_id,
            "ai_score",
            json.dumps(result, indent=2),
            channel="groq",
        )
        flash(f"Scored {result['score']}/100 ({result['tier']}).", "success")
        return redirect(url_for("lead_detail", lead_id=lead_id))

    @app.post("/leads/<int:lead_id>/outreach")
    def lead_outreach(lead_id: int):
        lead = db.get_lead(lead_id)
        if not lead:
            abort(404)
        channel = request.form.get("channel", "email")
        service = request.form.get("service", config.DEFAULT_SERVICES[0])
        tone = request.form.get("tone", "consultative")

        used_ai = ai.is_configured()
        if used_ai:
            try:
                draft = ai.generate_outreach(lead, channel=channel, service=service, tone=tone)
                draft["used_ai"] = True
            except ai.AIConfigError:
                used_ai = False
            except ai.AIError as exc:
                flash(f"AI draft failed: {exc}. Showing a template instead.", "error")
                used_ai = False
        if not used_ai:
            draft = outreach_templates.build_message(
                lead,
                channel=channel,
                service=service,
                tone=tone,
                sender={"name": config.SENDER_NAME, "company": config.SENDER_COMPANY},
            )

        content = draft.get("message", "")
        if draft.get("subject"):
            content = f"Subject: {draft['subject']}\n\n{content}"
        db.add_activity(lead_id, "outreach_draft", content, channel=channel)
        return render_lead(lead_id, draft=draft)

    @app.post("/leads/<int:lead_id>/chat")
    def lead_chat(lead_id: int):
        lead = db.get_lead(lead_id)
        if not lead:
            return jsonify(error="Lead not found."), 404

        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify(error="Send a JSON body with a messages array."), 400
        raw_messages = payload.get("messages")
        if not isinstance(raw_messages, list) or not raw_messages:
            return jsonify(error="A messages array is required."), 400
        if len(raw_messages) > ai.MAX_CHAT_MESSAGES:
            raw_messages = raw_messages[-ai.MAX_CHAT_MESSAGES:]

        messages = []
        for item in raw_messages:
            if not isinstance(item, dict):
                return jsonify(error="Each message must be an object."), 400
            role = item.get("role")
            content = item.get("content")
            if not isinstance(role, str) or role not in {"user", "assistant"}:
                return jsonify(error="Each message role must be user or assistant."), 400
            if not isinstance(content, str) or not content.strip():
                return jsonify(error="Each message needs text."), 400
            messages.append(
                {"role": role, "content": content.strip()[: ai.MAX_CHAT_CHARS]}
            )

        if messages[-1]["role"] != "user":
            return jsonify(error="The last message must be from the user."), 400

        try:
            reply = ai.chat_about_lead(lead, messages)
        except ai.AIConfigError as exc:
            return jsonify(error=str(exc)), 503
        except ai.AIError as exc:
            return jsonify(error=str(exc)), 502
        return jsonify(reply=reply)

    @app.post("/leads/<int:lead_id>/reply")
    def lead_reply(lead_id: int):
        lead = db.get_lead(lead_id)
        if not lead:
            abort(404)
        reply_text = (request.form.get("reply") or "").strip()
        if not reply_text:
            flash("Paste the reply first.", "error")
            return redirect(url_for("lead_detail", lead_id=lead_id))
        db.add_activity(lead_id, "reply", reply_text, channel=lead.get("platform", ""))

        analysis = None
        try:
            analysis = ai.summarize_reply(lead, reply_text)
            intent = analysis.get("intent")
            if intent == "interested":
                db.update_lead(lead_id, status="qualified")
            elif intent == "not_interested":
                db.update_lead(lead_id, status="lost")
            else:
                db.update_lead(lead_id, status="replied")
        except ai.AIConfigError as exc:
            flash(f"{exc} Reply logged without AI analysis.", "error")
            db.update_lead(lead_id, status="replied")
        except ai.AIError as exc:
            flash(f"Reply logged, but analysis failed: {exc}", "error")
            db.update_lead(lead_id, status="replied")

        return render_lead(lead_id, reply_analysis=analysis)

    @app.post("/leads/<int:lead_id>/activity")
    def lead_activity(lead_id: int):
        if not db.get_lead(lead_id):
            abort(404)
        kind = request.form.get("kind", "note")
        channel = request.form.get("channel", "")
        content = (request.form.get("content") or "").strip()
        if not content:
            flash("Activity text is empty.", "error")
            return redirect(url_for("lead_detail", lead_id=lead_id))
        db.add_activity(lead_id, kind, content, channel=channel)
        if request.form.get("mark_contacted"):
            db.update_lead(lead_id, status="contacted")
        flash("Activity logged.", "success")
        return redirect(url_for("lead_detail", lead_id=lead_id))

    @app.post("/leads/<int:lead_id>/audit")
    def lead_audit(lead_id: int):
        lead = db.get_lead(lead_id)
        if not lead:
            abort(404)
        url = (request.form.get("url") or lead.get("website") or "").strip()
        if not url:
            flash("This lead has no website. Add one first.", "error")
            return redirect(url_for("lead_detail", lead_id=lead_id))
        try:
            audit = website.audit_website(url, deep=True)
        except website.WebsiteError as exc:
            flash(f"Website audit failed: {exc}", "error")
            return redirect(url_for("lead_detail", lead_id=lead_id))

        updates = {}
        if audit["emails"] and not lead.get("email"):
            updates["email"] = audit["emails"][0]
        if audit["phones"] and not lead.get("phone"):
            updates["phone"] = audit["phones"][0]
        signals = []
        if not audit["has_chat"]:
            signals.append("No live chat")
        if not audit["has_booking"]:
            signals.append("No online booking")
        if audit["tech"]:
            signals.append("Tech: " + ", ".join(audit["tech"][:6]))
        if signals:
            existing = lead.get("notes", "")
            updates["notes"] = "\n".join(filter(None, [existing, " | ".join(signals)]))
        if updates:
            db.update_lead(lead_id, **updates)
        db.add_activity(lead_id, "website_audit", json.dumps(audit, indent=2), channel="website")
        flash("Website audited. Details saved to the activity log.", "success")
        return render_lead(lead_id, audit=audit)

    # ---------- Tools ----------
    @app.get("/tools")
    def tools():
        return render_template(
            "tools.html",
            ai_ready=ai.is_configured(),
            google_ready=bool(config.GOOGLE_PLACES_API_KEY),
            facebook_ready=bool(config.FACEBOOK_PAGE_ACCESS_TOKEN),
            groq_model=config.GROQ_MODEL,
        )

    @app.post("/tools/google")
    def tools_google():
        query = (request.form.get("query") or "").strip()
        location = (request.form.get("location") or "").strip()
        limit = _int(request.form.get("limit"), 20)
        enrich = bool(request.form.get("enrich"))
        try:
            found = google_places.search_places(
                query, location, limit=limit, with_details=True, enrich=enrich
            )
        except google_places.GooglePlacesError as exc:
            flash(str(exc), "error")
            return redirect(url_for("tools"))
        result = db.bulk_upsert(found)
        flash(
            f"Google Places: {result['created']} new, {result['updated']} updated, "
            f"{result['skipped']} skipped.",
            "success",
        )
        return redirect(url_for("leads"))

    @app.post("/tools/facebook")
    def tools_facebook():
        form_id = (request.form.get("form_id") or "").strip()
        limit = _int(request.form.get("limit"), 100)
        try:
            client = facebook.FacebookClient()
            found = client.fetch_form_leads(form_id, limit=limit)
        except facebook.FacebookError as exc:
            flash(str(exc), "error")
            return redirect(url_for("tools"))
        result = db.bulk_upsert(found)
        flash(
            f"Facebook leads: {result['created']} new, {result['updated']} updated, "
            f"{result['skipped']} skipped.",
            "success",
        )
        return redirect(url_for("leads"))

    @app.post("/tools/import")
    def tools_import():
        upload = request.files.get("file")
        if not upload or not upload.filename:
            flash("Choose a CSV file first.", "error")
            return redirect(url_for("tools"))
        try:
            parsed = csv_import.parse_csv(upload.stream)
        except ValueError as exc:
            flash(f"Import failed: {exc}", "error")
            return redirect(url_for("tools"))
        result = db.bulk_upsert(parsed["leads"])
        flash(
            f"CSV import: {result['created']} new, {result['updated']} updated, "
            f"{result['skipped']} skipped. Mapped columns: {', '.join(parsed['mapping'])}.",
            "success",
        )
        return redirect(url_for("leads"))

    @app.post("/tools/demo")
    def tools_demo():
        result = db.seed_demo()
        flash(
            f"Demo data: {result['created']} created, {result['updated']} already existed.",
            "success",
        )
        return redirect(url_for("leads"))

    # ---------- Export / API ----------
    @app.get("/export.csv")
    def export_csv():
        rows = db.list_leads(limit=100000)
        buffer = io.StringIO()
        columns = [
            "id", "name", "company", "email", "phone", "website", "platform",
            "profile_url", "location", "category", "status", "score", "angle",
            "notes", "source", "created_at", "updated_at", "last_contacted_at",
        ]
        writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        filename = f"leads-{datetime.now().strftime('%Y%m%d')}.csv"
        return Response(
            buffer.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/api/health")
    def api_health():
        return jsonify(
            {
                "status": "ok",
                "leads": db.stats()["total"],
                "groq": ai.is_configured(),
                "google_places": bool(config.GOOGLE_PLACES_API_KEY),
                "facebook": bool(config.FACEBOOK_PAGE_ACCESS_TOKEN),
                "db": str(db.get_db_path()),
            }
        )

    # ---------- Facebook webhook ----------
    @app.route("/webhooks/facebook", methods=["GET", "POST"])
    def facebook_webhook():
        if request.method == "GET":
            mode = request.args.get("hub.mode")
            token = request.args.get("hub.verify_token")
            challenge = request.args.get("hub.challenge", "")
            if mode == "subscribe" and token == config.FACEBOOK_VERIFY_TOKEN:
                return Response(challenge, mimetype="text/plain")
            abort(403)

        client = facebook.FacebookClient()
        raw = request.get_data()
        if not client.verify_signature(raw, request.headers.get("X-Hub-Signature-256")):
            abort(403)
        payload = request.get_json(silent=True) or {}
        events = client.parse_webhook(payload)
        imported = 0
        for event in events:
            if not event.get("lead_id"):
                continue
            try:
                lead = client.fetch_lead(event["lead_id"])
                db.upsert_lead(lead)
                imported += 1
            except facebook.FacebookError:
                continue
        app.logger.info("Facebook webhook: %s event(s), %s imported", len(events), imported)
        return Response("EVENT_RECEIVED", mimetype="text/plain")

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("404.html"), 404

    @app.errorhandler(413)
    def too_large(_error):
        flash("That file is too large (8 MB max).", "error")
        return redirect(url_for("tools"))

    return app


app = create_app()

if __name__ == "__main__":
    port = _int(os.getenv("PORT"), 5001)
    print(f"Lead Hunter running at http://127.0.0.1:{port}")
    app.run(host=os.getenv("HOST", "127.0.0.1"), port=port, debug=os.getenv("FLASK_DEBUG") == "1")
