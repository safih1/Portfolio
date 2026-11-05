"""Official Facebook (Meta) Graph API integration.

Only the documented Graph API is used: Page info, Lead Ads forms and lead
retrieval. This module deliberately does not scrape Facebook pages, log in as a
user, or send unsolicited DMs. Those actions violate Meta's terms and put the
account at risk.

Required permissions depend on the endpoint:
  - Page info: pages_read_engagement
  - Lead Ads: leads_retrieval (plus ads_management for some operations)
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any, Iterator

import requests

import config

DEFAULT_API_VERSION = "v21.0"


class FacebookError(RuntimeError):
    pass


def _first(data: dict, keys: list[str]) -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            value = value[0] if value else ""
        if value:
            return str(value).strip()
    return ""


class FacebookClient:
    def __init__(
        self,
        access_token: str | None = None,
        page_id: str | None = None,
        app_secret: str | None = None,
        api_version: str | None = None,
    ) -> None:
        self.access_token = (access_token or config.FACEBOOK_PAGE_ACCESS_TOKEN or "").strip()
        self.page_id = (page_id or config.FACEBOOK_PAGE_ID or "").strip()
        self.app_secret = (app_secret or config.FACEBOOK_APP_SECRET or "").strip()
        self.api_version = api_version or DEFAULT_API_VERSION
        self.base_url = f"https://graph.facebook.com/{self.api_version}"

    def _require_token(self) -> str:
        if not self.access_token:
            raise FacebookError(
                "FACEBOOK_PAGE_ACCESS_TOKEN is missing. Add a Page access token to .env."
            )
        return self.access_token

    def _get(self, path: str, params: dict | None = None) -> dict:
        params = dict(params or {})
        params["access_token"] = self._require_token()
        try:
            response = requests.get(f"{self.base_url}/{path.lstrip('/')}", params=params, timeout=25)
        except requests.RequestException as exc:
            raise FacebookError(f"Facebook request failed: {exc}") from exc
        try:
            data = response.json()
        except ValueError as exc:
            raise FacebookError(f"Facebook returned a non-JSON response ({response.status_code}).") from exc
        if response.status_code >= 400 or "error" in data:
            error = data.get("error", {})
            message = error.get("message") or f"HTTP {response.status_code}"
            code = error.get("code")
            raise FacebookError(f"Facebook API error {code or ''}: {message}".strip())
        return data

    def _paginate(self, path: str, params: dict, limit: int) -> Iterator[dict]:
        remaining = max(1, int(limit))
        data = self._get(path, params)
        while True:
            for item in data.get("data", []):
                if remaining <= 0:
                    return
                remaining -= 1
                yield item
            next_url = data.get("paging", {}).get("next")
            if not next_url or remaining <= 0:
                return
            # The next URL already contains the access token.
            try:
                response = requests.get(next_url, timeout=25)
                data = response.json()
            except (requests.RequestException, ValueError) as exc:
                raise FacebookError(f"Facebook pagination failed: {exc}") from exc
            if "error" in data:
                raise FacebookError(str(data["error"].get("message", "Pagination error")))

    def page_info(self, page_id: str | None = None) -> dict:
        page = (page_id or self.page_id).strip()
        if not page:
            raise FacebookError("FACEBOOK_PAGE_ID is missing.")
        return self._get(
            page,
            {
                "fields": (
                    "id,name,link,about,emails,phone,website,category,fan_count,"
                    "followers_count,location,cover"
                )
            },
        )

    def list_forms(self, page_id: str | None = None) -> list[dict]:
        page = (page_id or self.page_id).strip()
        if not page:
            raise FacebookError("FACEBOOK_PAGE_ID is missing.")
        data = self._get(
            f"{page}/leadgen_forms",
            {"fields": "id,name,status,created_time,leads_count", "limit": 100},
        )
        return data.get("data", [])

    def fetch_form_leads(self, form_id: str, limit: int = 100) -> list[dict]:
        form_id = (form_id or "").strip()
        if not form_id:
            raise FacebookError("A form ID is required.")
        items = self._paginate(
            f"{form_id}/leads",
            {
                "fields": (
                    "id,created_time,field_data,form_id,ad_id,ad_name,"
                    "campaign_id,campaign_name"
                ),
                "limit": min(100, max(1, int(limit))),
            },
            limit,
        )
        page = {}
        try:
            page = self.page_info()
        except FacebookError:
            page = {}
        return [self.normalize_leadgen(item, page) for item in items]

    def fetch_lead(self, lead_id: str) -> dict:
        lead_id = (lead_id or "").strip()
        if not lead_id:
            raise FacebookError("A lead ID is required.")
        item = self._get(
            lead_id,
            {
                "fields": (
                    "id,created_time,field_data,form_id,ad_id,ad_name,"
                    "campaign_id,campaign_name"
                )
            },
        )
        page = {}
        try:
            page = self.page_info()
        except FacebookError:
            pass
        return self.normalize_leadgen(item, page)

    @staticmethod
    def normalize_leadgen(item: dict, page: dict | None = None) -> dict:
        page = page or {}
        fields: dict[str, list[str]] = {}
        for entry in item.get("field_data", []) or []:
            name = str(entry.get("name", "")).strip()
            values = entry.get("values") or []
            if name:
                fields[name.lower()] = [str(value).strip() for value in values if str(value).strip()]

        flat = {key: (values[0] if values else "") for key, values in fields.items()}
        name = _first(flat, ["full_name", "name", "your_name", "contact_name"])
        if not name:
            first = _first(flat, ["first_name"])
            last = _first(flat, ["last_name"])
            name = " ".join(part for part in (first, last) if part)
        company = _first(flat, ["company_name", "company", "business_name", "organisation"])
        email = _first(flat, ["email", "email_address", "work_email"])
        phone = _first(
            flat,
            ["phone_number", "phone", "mobile", "mobile_number", "contact_number", "whatsapp_number"],
        )
        city = _first(flat, ["city", "town"])
        state = _first(flat, ["state", "province", "region"])
        country = _first(flat, ["country"])
        location = ", ".join(part for part in (city, state, country) if part)

        known = {
            "full_name", "name", "your_name", "contact_name", "first_name", "last_name",
            "company_name", "company", "business_name", "organisation", "email",
            "email_address", "work_email", "phone_number", "phone", "mobile",
            "mobile_number", "contact_number", "whatsapp_number", "city", "town",
            "state", "province", "region", "country",
        }
        extra = [f"{key}: {value}" for key, value in flat.items() if key not in known and value]
        notes = [f"Facebook lead ad ({item.get('form_id', 'form')})"]
        if item.get("campaign_name"):
            notes.append(f"Campaign: {item['campaign_name']}")
        if item.get("ad_name"):
            notes.append(f"Ad: {item['ad_name']}")
        if extra:
            notes.append("; ".join(extra))

        return {
            "name": name or email or phone or "Facebook lead",
            "company": company,
            "email": email,
            "phone": phone,
            "website": _first(flat, ["website", "website_url", "url"]),
            "platform": "facebook",
            "profile_url": page.get("link", ""),
            "location": location,
            "category": "facebook lead ad",
            "notes": " | ".join(notes),
            "source": "facebook_lead_ads",
        }

    # ---------- Webhook helpers ----------
    def verify_signature(self, raw_body: bytes, signature_header: str | None) -> bool:
        if not self.app_secret:
            return True  # Signature checking disabled when no app secret is set.
        if not signature_header or not signature_header.startswith("sha256="):
            return False
        expected = hmac.new(
            self.app_secret.encode("utf-8"), raw_body, hashlib.sha256
        ).hexdigest()
        received = signature_header.split("=", 1)[1]
        return hmac.compare_digest(expected, received)

    @staticmethod
    def parse_webhook(payload: dict) -> list[dict]:
        events: list[dict] = []
        for entry in payload.get("entry", []) or []:
            for change in entry.get("changes", []) or []:
                value = change.get("value", {}) or {}
                if change.get("field") == "leadgen" or value.get("leadgen_id"):
                    events.append(
                        {
                            "lead_id": str(value.get("leadgen_id") or ""),
                            "form_id": str(value.get("form_id") or ""),
                            "page_id": str(value.get("page_id") or entry.get("id") or ""),
                            "ad_id": str(value.get("ad_id") or ""),
                            "created_time": value.get("created_time"),
                        }
                    )
        return events


def poll_form(form_id: str, limit: int = 100) -> list[dict]:
    """Convenience polling helper used by the CLI."""
    return FacebookClient().fetch_form_leads(form_id, limit=limit)
