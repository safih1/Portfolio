from __future__ import annotations

from providers import website

HTML = """
<!doctype html>
<html>
<head>
  <title>Bright Smile Dental</title>
  <meta name="description" content="Family dental clinic in Austin." />
</head>
<body>
  <a href="mailto:hello@brightsmile.com">Email us</a>
  <a href="tel:+15125550134">Call us</a>
  <a href="https://facebook.com/brightsmile">Facebook</a>
  <a href="https://www.instagram.com/brightsmile">Instagram</a>
  <form><input name="email" /></form>
  <script src="https://cdn.shopify.com/s/files/x.js"></script>
  <p>We care about teeth.</p>
</body>
</html>
"""


def test_normalize_url_adds_scheme():
    assert website.normalize_url("example.com") == "https://example.com"


def test_private_hosts_rejected():
    assert website._is_public_host("localhost") is False
    assert website._is_public_host("127.0.0.1") is False


def test_extract_emails_filters_noise():
    text = "hello@site.com logo@2x.png test@example.com"
    emails = website.extract_emails(text)
    assert emails == ["hello@site.com"]


def test_audit_website(monkeypatch):
    monkeypatch.setattr(
        website, "_get", lambda url, timeout=15: (url, HTML)
    )
    audit = website.audit_website("https://brightsmile.com", deep=False)
    assert audit["title"] == "Bright Smile Dental"
    assert "hello@brightsmile.com" in audit["emails"]
    assert audit["phones"]
    assert audit["socials"]["facebook"].startswith("https://facebook.com")
    assert audit["has_contact_form"] is True
    assert "Shopify" in audit["tech"]
    assert audit["signals"]["no_chat"] is True


def test_audit_rejects_private(monkeypatch):
    try:
        website.audit_website("http://127.0.0.1:8000")
    except website.WebsiteError:
        pass
    else:
        raise AssertionError("Private hosts must be rejected")
