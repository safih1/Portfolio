"""Google Places (legacy Text Search + Details) lead source."""

from __future__ import annotations

import time

import requests

import config
from providers.website import WebsiteError, audit_website

TEXT_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"


class GooglePlacesError(RuntimeError):
    pass


def _api_key(api_key: str | None) -> str:
    key = (api_key or config.GOOGLE_PLACES_API_KEY or "").strip()
    if not key:
        raise GooglePlacesError(
            "GOOGLE_PLACES_API_KEY is missing. Add a key with Places API enabled."
        )
    return key


def _request(url: str, params: dict) -> dict:
    try:
        response = requests.get(url, params=params, timeout=20)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise GooglePlacesError(f"Google Places request failed: {exc}") from exc
    data = response.json()
    status = data.get("status")
    if status == "ZERO_RESULTS":
        return {"results": []}
    if status not in {"OK"}:
        message = data.get("error_message") or status or "Unknown error"
        raise GooglePlacesError(f"Google Places error: {message}")
    return data


def _details(place_id: str, key: str) -> dict:
    data = _request(
        DETAILS_URL,
        {
            "place_id": place_id,
            "fields": (
                "name,formatted_address,formatted_phone_number,international_phone_number,"
                "website,rating,user_ratings_total,url,types,business_status"
            ),
            "key": key,
        },
    )
    return data.get("result", {})


def search_places(
    query: str,
    location: str = "",
    limit: int = 20,
    with_details: bool = True,
    enrich: bool = False,
    api_key: str | None = None,
) -> list[dict]:
    """Search Google Places and return normalized leads."""
    query = (query or "").strip()
    if not query:
        raise GooglePlacesError("A search query is required.")
    key = _api_key(api_key)
    text_query = f"{query} in {location}".strip() if location else query
    limit = max(1, min(60, int(limit)))

    results: list[dict] = []
    token: str | None = None
    while len(results) < limit:
        params = {"query": text_query, "key": key}
        if token:
            params["pagetoken"] = token
        data = _request(TEXT_SEARCH_URL, params)
        results.extend(data.get("results", []))
        token = data.get("next_page_token")
        if not token or len(results) >= limit:
            break
        time.sleep(1.6)  # Google requires a short delay before the token is valid.

    leads: list[dict] = []
    for place in results[:limit]:
        details: dict = {}
        if with_details and place.get("place_id"):
            try:
                details = _details(place["place_id"], key)
            except GooglePlacesError:
                details = {}
        name = details.get("name") or place.get("name") or "Unknown business"
        website = details.get("website", "")
        rating = details.get("rating", place.get("rating"))
        reviews = details.get("user_ratings_total", place.get("user_ratings_total"))
        types = details.get("types") or place.get("types") or []
        notes = []
        if rating:
            notes.append(f"Google rating: {rating} ({reviews or 0} reviews)")
        if details.get("business_status") and details["business_status"] != "OPERATIONAL":
            notes.append(f"Status: {details['business_status']}")

        lead = {
            "name": name,
            "company": name,
            "email": "",
            "phone": details.get("formatted_phone_number")
            or details.get("international_phone_number", ""),
            "website": website,
            "platform": "google",
            "profile_url": details.get("url")
            or f"https://www.google.com/maps/place/?q=place_id:{place.get('place_id', '')}",
            "location": details.get("formatted_address") or place.get("formatted_address", ""),
            "category": types[0].replace("_", " ") if types else query,
            "notes": " | ".join(notes),
            "source": "google_places",
        }

        if enrich and website:
            try:
                audit = audit_website(website, deep=True)
                lead["email"] = audit["emails"][0] if audit["emails"] else ""
                extra = []
                if audit.get("has_chat") is False:
                    extra.append("No live chat detected")
                if audit.get("has_booking") is False:
                    extra.append("No online booking detected")
                if audit.get("tech"):
                    extra.append("Tech: " + ", ".join(audit["tech"][:5]))
                if extra:
                    lead["notes"] = " | ".join(filter(None, [lead["notes"], " | ".join(extra)]))
            except WebsiteError:
                pass
        leads.append(lead)
    return leads
