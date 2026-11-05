from __future__ import annotations

import io

from providers import csv_import


def test_detect_mapping():
    mapping = csv_import.detect_mapping(
        ["Full Name", "Business Name", "E-mail", "Phone Number", "Website", "City"]
    )
    assert mapping["name"] == "Full Name"
    assert mapping["company"] == "Business Name"
    assert mapping["email"] == "E-mail"
    assert mapping["phone"] == "Phone Number"
    assert mapping["website"] == "Website"
    assert mapping["location"] == "City"


def test_parse_csv_merges_aliases():
    content = (
        "full_name,business_name,email,phone_number,notes\n"
        "Amelia Hart,Bright Smile,amelia@example.com,5125550100,Misses after-hours calls\n"
        ",,,,,,\n"
    )
    parsed = csv_import.parse_csv(io.BytesIO(content.encode("utf-8")))
    assert parsed["total"] == 2
    assert parsed["skipped"] == 1
    lead = parsed["leads"][0]
    assert lead["name"] == "Amelia Hart"
    assert lead["company"] == "Bright Smile"
    assert lead["platform"] == "csv"


def test_parse_csv_rejects_unknown_headers():
    content = "foo,bar\n1,2\n"
    try:
        csv_import.parse_csv(io.StringIO(content))
    except ValueError:
        pass
    else:
        raise AssertionError("Unknown headers should be rejected")


def test_semicolon_delimiter():
    content = "name;email\nSam;sam@example.com\n"
    parsed = csv_import.parse_csv(io.StringIO(content))
    assert parsed["leads"][0]["email"] == "sam@example.com"
