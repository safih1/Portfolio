from __future__ import annotations

import ai
from outreach import templates


def test_parse_json_plain():
    assert ai.parse_json('{"score": 80}') == {"score": 80}


def test_parse_json_fenced():
    assert ai.parse_json('```json\n{"score": 70}\n```') == {"score": 70}


def test_parse_json_with_prose():
    assert ai.parse_json('Here you go: {"tier": "hot"} thanks') == {"tier": "hot"}


def test_template_email_mentions_company():
    draft = templates.build_message(
        {"name": "Amelia Hart", "company": "Bright Smile"},
        channel="email",
        service="AI receptionist / voice agent",
    )
    assert "Bright Smile" in draft["message"]
    assert draft["subject"]
    assert draft["used_ai"] is False


def test_template_dm_has_no_subject():
    draft = templates.build_message(
        {"name": "Marcus Lee", "company": "Northline Roofing"},
        channel="facebook_dm",
    )
    assert draft["subject"] == ""
    assert "Northline Roofing" in draft["message"]


def test_template_unknown_service_falls_back():
    draft = templates.build_message(
        {"name": "Test", "company": "Test Co"},
        channel="linkedin",
        service="Something custom",
    )
    assert "Something custom" in draft["message"] or "automation" in draft["message"]
