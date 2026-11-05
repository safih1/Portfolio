"""Flexible CSV import for exported lead lists (Facebook, LinkedIn, Apollo, etc.)."""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import IO, Any

ALIASES: dict[str, list[str]] = {
    "name": [
        "name", "full_name", "full name", "contact_name", "contact name",
        "lead_name", "lead name", "person", "first_name", "first name",
    ],
    "company": [
        "company", "company_name", "company name", "business", "business_name",
        "business name", "organization", "organisation", "org",
    ],
    "email": [
        "email", "e-mail", "email_address", "email address", "work_email",
        "work email", "contact_email", "contact email",
    ],
    "phone": [
        "phone", "phone_number", "phone number", "mobile", "mobile_number",
        "mobile number", "telephone", "tel", "cell", "whatsapp",
    ],
    "website": [
        "website", "web_site", "web site", "company_website", "company website",
        "domain", "site", "url",
    ],
    "location": [
        "location", "city", "address", "country", "region", "state", "area",
    ],
    "category": [
        "category", "industry", "niche", "type", "vertical", "sector",
    ],
    "platform": [
        "platform", "source", "network", "channel", "origin",
    ],
    "profile_url": [
        "profile_url", "profile url", "profile", "linkedin_url", "linkedin url",
        "facebook_url", "facebook url", "facebook_profile", "page_url",
    ],
    "notes": [
        "notes", "note", "description", "comments", "comment", "message", "details",
    ],
    "status": ["status", "stage", "lead_status", "lead status"],
}


def _normalize_header(value: str) -> str:
    return " ".join((value or "").strip().lower().replace("_", " ").split())


def detect_mapping(headers: list[str]) -> dict[str, str]:
    """Map canonical fields to the actual CSV headers."""
    normalized = {_normalize_header(header): header for header in headers if header}
    mapping: dict[str, str] = {}
    used: set[str] = set()
    for field, aliases in ALIASES.items():
        for alias in aliases:
            key = _normalize_header(alias)
            if key in normalized and normalized[key] not in used:
                mapping[field] = normalized[key]
                used.add(normalized[key])
                break
    # "url" can mean website or profile. Prefer website unless a profile field exists.
    if "website" not in mapping and "profile_url" in mapping:
        mapping["website"] = mapping["profile_url"]
    return mapping


def _read_text(source: str | Path | IO[bytes] | IO[str]) -> str:
    if hasattr(source, "read"):
        raw = source.read()  # type: ignore[union-attr]
        if isinstance(raw, bytes):
            for encoding in ("utf-8-sig", "utf-8", "latin-1"):
                try:
                    return raw.decode(encoding)
                except UnicodeDecodeError:
                    continue
            return raw.decode("utf-8", errors="replace")
        return str(raw)
    path = Path(source)
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def parse_csv(source: str | Path | IO[bytes] | IO[str]) -> dict[str, Any]:
    text = _read_text(source)
    if not text.strip():
        raise ValueError("The CSV file is empty.")

    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    headers = [header for header in (reader.fieldnames or []) if header]
    if not headers:
        raise ValueError("No column headers found in the CSV.")

    mapping = detect_mapping(headers)
    if "name" not in mapping and "email" not in mapping and "phone" not in mapping:
        raise ValueError(
            "Could not find name, email, or phone columns. Rename the headers and try again."
        )

    leads: list[dict] = []
    skipped = 0
    for row in reader:
        record: dict[str, str] = {}
        for field, header in mapping.items():
            value = row.get(header, "")
            record[field] = str(value).strip() if value is not None else ""
        if not any(record.get(field) for field in ("name", "email", "phone", "company")):
            skipped += 1
            continue
        record.setdefault("platform", "csv")
        if not record.get("platform"):
            record["platform"] = "csv"
        record.setdefault("source", "csv_import")
        leads.append(record)

    return {
        "leads": leads,
        "mapping": mapping,
        "headers": headers,
        "total": len(leads) + skipped,
        "skipped": skipped,
    }


def write_csv(rows: list[dict], columns: list[str] | None = None) -> str:
    if not rows:
        return ""
    columns = columns or list(rows[0].keys())
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()
