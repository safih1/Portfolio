"""SQLite storage for leads and activities."""

from __future__ import annotations

import csv
import io
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import config

STATUSES = ("new", "contacted", "replied", "qualified", "won", "lost")
LEAD_FIELDS = (
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
    "score_reason",
    "angle",
    "source",
)

_db_path: Path = config.DB_PATH


def set_db_path(path: str | Path) -> None:
    """Point the module at a different database (used by tests)."""
    global _db_path
    _db_path = Path(path)
    _db_path.parent.mkdir(parents=True, exist_ok=True)


def get_db_path() -> Path:
    return _db_path


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    _db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_db_path, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def connection():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    company         TEXT NOT NULL DEFAULT '',
    email           TEXT NOT NULL DEFAULT '',
    phone           TEXT NOT NULL DEFAULT '',
    website         TEXT NOT NULL DEFAULT '',
    platform        TEXT NOT NULL DEFAULT 'manual',
    profile_url     TEXT NOT NULL DEFAULT '',
    location        TEXT NOT NULL DEFAULT '',
    category        TEXT NOT NULL DEFAULT '',
    notes           TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'new',
    score           INTEGER,
    score_reason    TEXT NOT NULL DEFAULT '',
    angle           TEXT NOT NULL DEFAULT '',
    source          TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    last_contacted_at TEXT
);

CREATE TABLE IF NOT EXISTS activities (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id     INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL,
    channel     TEXT NOT NULL DEFAULT '',
    content     TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_leads_email ON leads(email);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_platform ON leads(platform);
CREATE INDEX IF NOT EXISTS idx_leads_updated ON leads(updated_at);
CREATE INDEX IF NOT EXISTS idx_activities_lead ON activities(lead_id);
"""


def init_db() -> None:
    with connection() as conn:
        conn.executescript(SCHEMA)


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def _url_key(value: str) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"^https?://", "", value)
    value = re.sub(r"^www\.", "", value)
    return value.rstrip("/")


def _score_value(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return max(0, min(100, int(float(value))))
    except (TypeError, ValueError):
        return None


def normalize_lead(data: dict) -> dict:
    lead = {field: (data.get(field) or "") for field in LEAD_FIELDS}
    lead["name"] = str(lead["name"]).strip()
    lead["company"] = str(lead["company"]).strip()
    lead["email"] = str(lead["email"]).strip()
    lead["phone"] = str(lead["phone"]).strip()
    lead["website"] = str(lead["website"]).strip()
    lead["platform"] = (str(lead["platform"]).strip() or "manual").lower()
    lead["profile_url"] = str(lead["profile_url"]).strip()
    lead["location"] = str(lead["location"]).strip()
    lead["category"] = str(lead["category"]).strip()
    lead["notes"] = str(lead["notes"]).strip()
    lead["status"] = str(lead["status"]).strip().lower() or "new"
    if lead["status"] not in STATUSES:
        lead["status"] = "new"
    lead["score"] = _score_value(lead["score"])
    lead["score_reason"] = str(lead["score_reason"]).strip()
    lead["angle"] = str(lead["angle"]).strip()
    lead["source"] = str(lead["source"]).strip()
    for field in ("name", "company", "email", "phone", "website", "profile_url"):
        lead[field] = lead[field][:500]
    lead["notes"] = lead["notes"][:5000]
    return lead


def _find_duplicate(conn: sqlite3.Connection, lead: dict) -> sqlite3.Row | None:
    email = lead["email"].lower()
    if email:
        row = conn.execute(
            "SELECT * FROM leads WHERE lower(email) = ? LIMIT 1", (email,)
        ).fetchone()
        if row:
            return row

    phone = _digits(lead["phone"])
    if len(phone) >= 7:
        for row in conn.execute("SELECT * FROM leads WHERE phone != ''").fetchall():
            if _digits(row["phone"]) == phone:
                return row

    website = _url_key(lead["website"])
    if website:
        row = conn.execute(
            "SELECT * FROM leads WHERE lower(replace(replace(website,'https://',''),'http://','')) LIKE ? LIMIT 1",
            (f"%{website}%",),
        ).fetchone()
        if row:
            return row

    if lead["name"] and lead["company"]:
        row = conn.execute(
            "SELECT * FROM leads WHERE lower(name) = ? AND lower(company) = ? LIMIT 1",
            (lead["name"].lower(), lead["company"].lower()),
        ).fetchone()
        if row:
            return row
    return None


def upsert_lead(data: dict) -> tuple[int, bool]:
    """Insert or merge a lead. Returns (lead_id, created)."""
    lead = normalize_lead(data)
    if not lead["name"]:
        lead["name"] = lead["company"] or lead["email"] or lead["phone"] or "Unknown lead"

    now = utcnow()
    with connection() as conn:
        existing = _find_duplicate(conn, lead)
        if existing:
            merged: dict[str, Any] = {}
            for field in LEAD_FIELDS:
                new_value = lead[field]
                old_value = existing[field]
                if new_value in (None, ""):
                    continue
                if field == "status":
                    if common_status_rank(new_value) > common_status_rank(old_value):
                        merged[field] = new_value
                elif field == "score":
                    if old_value is None:
                        merged[field] = new_value
                elif field == "notes":
                    old_notes = (old_value or "").strip()
                    new_notes = str(new_value).strip()
                    if old_notes and new_notes not in old_notes:
                        merged[field] = f"{old_notes}\n{new_notes}"
                    elif not old_notes:
                        merged[field] = new_notes
                elif old_value in (None, "") or field in {"score_reason", "angle"}:
                    merged[field] = new_value
            if merged:
                merged["updated_at"] = now
                assignments = ", ".join(f"{field} = ?" for field in merged)
                conn.execute(
                    f"UPDATE leads SET {assignments} WHERE id = ?",
                    (*merged.values(), existing["id"]),
                )
            return int(existing["id"]), False

        columns = ", ".join(LEAD_FIELDS + ("created_at", "updated_at"))
        placeholders = ", ".join("?" for _ in range(len(LEAD_FIELDS) + 2))
        values = [lead[field] for field in LEAD_FIELDS] + [now, now]
        cursor = conn.execute(
            f"INSERT INTO leads ({columns}) VALUES ({placeholders})", values
        )
        return int(cursor.lastrowid), True


def common_status_rank(status: str) -> int:
    order = {"new": 0, "contacted": 1, "replied": 2, "qualified": 3, "won": 4, "lost": 1}
    return order.get(status or "new", 0)


def bulk_upsert(leads: Iterable[dict]) -> dict:
    created = updated = skipped = 0
    for lead in leads:
        if not (lead.get("name") or lead.get("email") or lead.get("phone") or lead.get("company")):
            skipped += 1
            continue
        _, is_new = upsert_lead(lead)
        if is_new:
            created += 1
        else:
            updated += 1
    return {"created": created, "updated": updated, "skipped": skipped}


def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row else None


def get_lead(lead_id: int) -> dict | None:
    with connection() as conn:
        return _row_to_dict(
            conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
        )


def update_lead(lead_id: int, **fields: Any) -> bool:
    allowed = set(LEAD_FIELDS)
    updates = {key: value for key, value in fields.items() if key in allowed}
    if not updates:
        return False
    if "status" in updates and updates["status"] not in STATUSES:
        raise ValueError(f"Invalid status: {updates['status']}")
    if "score" in updates:
        updates["score"] = _score_value(updates["score"])
    updates["updated_at"] = utcnow()
    if updates.get("status") in {"contacted", "replied"}:
        updates["last_contacted_at"] = updates["updated_at"]

    assignments = ", ".join(f"{field} = ?" for field in updates)
    with connection() as conn:
        cursor = conn.execute(
            f"UPDATE leads SET {assignments} WHERE id = ?",
            (*updates.values(), lead_id),
        )
        return cursor.rowcount > 0


def delete_lead(lead_id: int) -> bool:
    with connection() as conn:
        cursor = conn.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
        return cursor.rowcount > 0


def list_leads(
    query: str = "",
    status: str = "",
    platform: str = "",
    min_score: int | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[dict]:
    clauses: list[str] = []
    params: list[Any] = []
    if query:
        like = f"%{query.strip()}%"
        clauses.append(
            "(name LIKE ? OR company LIKE ? OR email LIKE ? OR phone LIKE ? OR website LIKE ? OR location LIKE ? OR category LIKE ? OR notes LIKE ?)"
        )
        params.extend([like] * 8)
    if status:
        clauses.append("status = ?")
        params.append(status)
    if platform:
        clauses.append("platform = ?")
        params.append(platform)
    if min_score is not None:
        clauses.append("COALESCE(score, 0) >= ?")
        params.append(min_score)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.extend([max(1, min(1000, limit)), max(0, offset)])
    with connection() as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM leads
            {where}
            ORDER BY COALESCE(score, -1) DESC, updated_at DESC
            LIMIT ? OFFSET ?
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def count_leads(query: str = "", status: str = "", platform: str = "") -> int:
    clauses: list[str] = []
    params: list[Any] = []
    if query:
        like = f"%{query}%"
        clauses.append(
            "(name LIKE ? OR company LIKE ? OR email LIKE ? OR phone LIKE ? OR website LIKE ? OR location LIKE ? OR category LIKE ? OR notes LIKE ?)"
        )
        params.extend([like] * 8)
    if status:
        clauses.append("status = ?")
        params.append(status)
    if platform:
        clauses.append("platform = ?")
        params.append(platform)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with connection() as conn:
        row = conn.execute(f"SELECT COUNT(*) AS n FROM leads {where}", params).fetchone()
    return int(row["n"])


def add_activity(
    lead_id: int, kind: str, content: str, channel: str = ""
) -> int:
    with connection() as conn:
        cursor = conn.execute(
            "INSERT INTO activities (lead_id, kind, channel, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (lead_id, kind[:50], channel[:50], content[:10000], utcnow()),
        )
        return int(cursor.lastrowid)


def list_activities(lead_id: int, limit: int = 100) -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT * FROM activities WHERE lead_id = ? ORDER BY created_at DESC LIMIT ?",
            (lead_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def stats() -> dict:
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat(timespec="seconds")
    with connection() as conn:
        total = conn.execute("SELECT COUNT(*) AS n FROM leads").fetchone()["n"]
        by_status = {status: 0 for status in STATUSES}
        for row in conn.execute("SELECT status, COUNT(*) AS n FROM leads GROUP BY status"):
            by_status[row["status"]] = row["n"]
        by_platform = [
            dict(row)
            for row in conn.execute(
                "SELECT platform, COUNT(*) AS n FROM leads GROUP BY platform ORDER BY n DESC"
            )
        ]
        avg_score = conn.execute(
            "SELECT AVG(score) AS n FROM leads WHERE score IS NOT NULL"
        ).fetchone()["n"]
        new_week = conn.execute(
            "SELECT COUNT(*) AS n FROM leads WHERE created_at >= ?", (week_ago,)
        ).fetchone()["n"]
        hot = conn.execute(
            "SELECT COUNT(*) AS n FROM leads WHERE COALESCE(score, 0) >= 70"
        ).fetchone()["n"]
        followups = conn.execute(
            "SELECT COUNT(*) AS n FROM leads WHERE status IN ('contacted','replied') AND updated_at < ?",
            ((datetime.now(timezone.utc) - timedelta(days=3)).isoformat(timespec="seconds"),),
        ).fetchone()["n"]
    return {
        "total": total,
        "by_status": by_status,
        "by_platform": by_platform,
        "avg_score": round(avg_score, 1) if avg_score is not None else None,
        "new_this_week": new_week,
        "hot": hot,
        "needs_followup": followups,
    }


def export_rows(rows: list[dict] | None = None) -> str:
    rows = rows if rows is not None else list_leads(limit=1000)
    columns = [
        "id",
        "name",
        "company",
        "email",
        "phone",
        "website",
        "platform",
        "profile_url",
        "location",
        "category",
        "status",
        "score",
        "angle",
        "notes",
        "source",
        "created_at",
        "updated_at",
        "last_contacted_at",
    ]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def seed_demo() -> dict:
    demo = [
        {
            "name": "Dr. Amelia Hart",
            "company": "Bright Smile Dental",
            "email": "hello@brightsmiledemo.com",
            "phone": "+1 512 555 0134",
            "website": "https://brightsmiledemo.com",
            "platform": "google",
            "location": "Austin, TX",
            "category": "dentist",
            "source": "demo",
            "notes": "Busy practice, phone-heavy booking process.",
        },
        {
            "name": "Marcus Lee",
            "company": "Northline Roofing",
            "email": "marcus@northlineroofingdemo.com",
            "phone": "+1 214 555 0177",
            "website": "https://northlineroofingdemo.com",
            "platform": "facebook",
            "location": "Dallas, TX",
            "category": "roofing contractor",
            "source": "demo",
            "notes": "Runs Facebook lead ads. Leads wait hours for a reply.",
        },
        {
            "name": "Sofia Rivera",
            "company": "Casa Verde Realty",
            "email": "sofia@casaverdedemo.com",
            "phone": "+1 305 555 0192",
            "website": "https://casaverdedemo.com",
            "platform": "linkedin",
            "location": "Miami, FL",
            "category": "real estate agency",
            "source": "demo",
            "notes": "Small team, no CRM, follows up from a spreadsheet.",
        },
    ]
    return bulk_upsert(demo)
