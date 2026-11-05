"""Website audit and email discovery."""

from __future__ import annotations

import ipaddress
import re
import socket
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 LeadHunter/1.0"
)
MAX_BYTES = 1_500_000
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+?\d{1,3}[\s.\-()]{0,3})?(?:\(?\d{2,4}\)?[\s.\-()]{0,2}){2,4}\d{2,4}")

BAD_EMAIL_PARTS = (
    "example.com",
    "example.org",
    "sentry.io",
    "wixpress.com",
    "domain.com",
    "email.com",
    "yourdomain",
    "yoursite",
    "sentry-next",
    "png",
    "jpg",
    "jpeg",
    "gif",
    "webp",
    "svg",
)

SOCIAL_PATTERNS = {
    "facebook": r"https?://(?:www\.)?facebook\.com/[A-Za-z0-9_.\-/]+",
    "instagram": r"https?://(?:www\.)?instagram\.com/[A-Za-z0-9_.\-/]+",
    "linkedin": r"https?://(?:[a-z]{2,3}\.)?linkedin\.com/(?:company|in|school)/[A-Za-z0-9_.\-/]+",
    "twitter": r"https?://(?:www\.)?(?:twitter|x)\.com/[A-Za-z0-9_]+",
    "tiktok": r"https?://(?:www\.)?tiktok\.com/@[A-Za-z0-9_.]+",
    "youtube": r"https?://(?:www\.)?youtube\.com/(?:@|channel/|c/)[A-Za-z0-9_.\-/]+",
    "whatsapp": r"https?://(?:wa\.me|api\.whatsapp\.com)/[A-Za-z0-9+?=&/%\-]+",
}

TECH_HINTS = {
    "WordPress": ("wp-content", "wp-json", "wordpress"),
    "Shopify": ("cdn.shopify.com", "shopify"),
    "Wix": ("wixstatic.com", "wix.com"),
    "Squarespace": ("squarespace.com", "static1.squarespace"),
    "Webflow": ("webflow.io", "webflow.com"),
    "HubSpot": ("hs-scripts.com", "hubspot.com"),
    "Calendly": ("calendly.com",),
    "Cal.com": ("cal.com",),
    "Mailchimp": ("mailchimp.com", "list-manage.com"),
    "Klaviyo": ("klaviyo.com",),
    "Intercom": ("intercom.io", "intercomcdn.com"),
    "Drift": ("drift.com", "driftt.com"),
    "Tawk.to": ("tawk.to",),
    "Crisp": ("crisp.chat",),
    "Tidio": ("tidio.com", "tidio.co"),
    "Zendesk": ("zendesk.com", "zopim.com"),
    "GoHighLevel": ("msgsndr.com", "gohighlevel.com"),
    "Stripe": ("stripe.com", "js.stripe.com"),
    "Google Analytics": ("googletagmanager.com", "google-analytics.com"),
}

CHAT_HINTS = ("intercom", "drift", "tawk", "crisp", "tidio", "livechat", "zendesk", "zopim")
BOOKING_HINTS = ("calendly", "cal.com", "acuityscheduling", "booksy", "setmore", "squareup.com/appointments")


class WebsiteError(RuntimeError):
    pass


def normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        raise WebsiteError("A website URL is required.")
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    parsed = urlparse(url)
    if not parsed.hostname:
        raise WebsiteError(f"Invalid URL: {url}")
    return parsed.geturl()


def _is_public_host(hostname: str) -> bool:
    hostname = (hostname or "").strip().lower()
    if not hostname or hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
        return False
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(hostname, None)}
    except socket.gaierror:
        return False
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
    return True


def _get(url: str, timeout: int = 15) -> tuple[str, str]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise WebsiteError("Only http and https URLs are supported.")
    if not _is_public_host(parsed.hostname or ""):
        raise WebsiteError("That host is private or could not be resolved.")

    try:
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
            timeout=timeout,
            stream=True,
            allow_redirects=True,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise WebsiteError(f"Could not load the site: {exc}") from exc

    final_host = urlparse(response.url).hostname or ""
    if not _is_public_host(final_host):
        response.close()
        raise WebsiteError("The site redirected to a private address.")

    content_type = response.headers.get("content-type", "")
    if "html" not in content_type and content_type:
        response.close()
        raise WebsiteError(f"Expected an HTML page, got {content_type}.")

    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_content(chunk_size=65536):
        if not chunk:
            continue
        chunks.append(chunk)
        total += len(chunk)
        if total >= MAX_BYTES:
            break
    response.close()
    encoding = response.encoding or "utf-8"
    return response.url, b"".join(chunks).decode(encoding, errors="replace")


def clean_emails(values: list[str]) -> list[str]:
    found: list[str] = []
    for value in values:
        email = value.strip().strip(".,;:").lower()
        if not email or any(part in email for part in BAD_EMAIL_PARTS):
            continue
        if len(email) > 254 or email.count("@") != 1:
            continue
        if email not in found:
            found.append(email)
    return found


def extract_emails(text: str) -> list[str]:
    return clean_emails(EMAIL_RE.findall(text or ""))


def _extract_phones(soup: BeautifulSoup, text: str) -> list[str]:
    candidates: list[str] = []
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if href.lower().startswith("tel:"):
            candidates.append(href[4:].strip())
    for match in PHONE_RE.findall(text or ""):
        digits = re.sub(r"\D", "", match)
        if 9 <= len(digits) <= 15:
            candidates.append(match.strip())
    result: list[str] = []
    for phone in candidates:
        digits = re.sub(r"\D", "", phone)
        if 9 <= len(digits) <= 15 and phone not in result:
            result.append(phone)
    return result[:5]


def _extract_socials(html: str) -> dict[str, str]:
    socials: dict[str, str] = {}
    for name, pattern in SOCIAL_PATTERNS.items():
        match = re.search(pattern, html, re.I)
        if match:
            socials[name] = match.group(0).rstrip('"\'')
    return socials


def _detect_tech(html: str) -> list[str]:
    lower = (html or "").lower()
    return sorted(
        label for label, needles in TECH_HINTS.items() if any(needle in lower for needle in needles)
    )


def _parse_page(url: str, html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    description = ""
    meta = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    if meta and meta.get("content"):
        description = meta["content"].strip()
    if not description:
        og = soup.find("meta", attrs={"property": "og:description"})
        if og and og.get("content"):
            description = og["content"].strip()

    text = soup.get_text(" ", strip=True)
    mailto = []
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if href.lower().startswith("mailto:"):
            mailto.append(href[7:].split("?")[0])

    lower = html.lower()
    emails = clean_emails(mailto + EMAIL_RE.findall(html))
    return {
        "url": url,
        "title": title[:300],
        "description": description[:500],
        "emails": emails[:10],
        "phones": _extract_phones(soup, text),
        "socials": _extract_socials(html),
        "tech": _detect_tech(html),
        "has_contact_form": bool(soup.find("form")),
        "has_chat": any(hint in lower for hint in CHAT_HINTS),
        "has_booking": any(hint in lower for hint in BOOKING_HINTS),
        "word_count": len(text.split()),
    }


def audit_website(url: str, deep: bool = True) -> dict:
    normalized = normalize_url(url)
    final_url, html = _get(normalized)
    result = _parse_page(final_url, html)

    if deep and not result["emails"]:
        # Try the two most common contact pages on the same host.
        base = f"{urlparse(final_url).scheme}://{urlparse(final_url).netloc}"
        for path in ("/contact", "/about"):
            try:
                page_url, page_html = _get(urljoin(base, path))
                extra = _parse_page(page_url, page_html)
                for email in extra["emails"]:
                    if email not in result["emails"]:
                        result["emails"].append(email)
                for phone in extra["phones"]:
                    if phone not in result["phones"]:
                        result["phones"].append(phone)
                if result["emails"]:
                    break
            except WebsiteError:
                continue

    result["audited_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    result["signals"] = {
        "no_chat": not result["has_chat"],
        "no_booking": not result["has_booking"],
        "has_email": bool(result["emails"]),
        "has_phone": bool(result["phones"]),
        "has_social": bool(result["socials"]),
    }
    return result


def find_email(url: str) -> str:
    audit = audit_website(url, deep=True)
    return audit["emails"][0] if audit["emails"] else ""
