from __future__ import annotations

import db


def fresh_db(tmp_path):
    db.set_db_path(tmp_path / "test.db")
    db.init_db()


def test_upsert_and_deduplicate(tmp_path):
    fresh_db(tmp_path)
    lead_id, created = db.upsert_lead(
        {"name": "Amelia Hart", "company": "Bright Smile", "email": "A@Example.com"}
    )
    assert created is True

    same_id, created_again = db.upsert_lead(
        {"name": "Amelia Hart", "company": "Bright Smile", "email": "a@example.com", "phone": "5125550100"}
    )
    assert same_id == lead_id
    assert created_again is False

    lead = db.get_lead(lead_id)
    assert lead["phone"] == "5125550100"
    assert lead["email"].lower() == "a@example.com"


def test_update_and_stats(tmp_path):
    fresh_db(tmp_path)
    lead_id, _ = db.upsert_lead({"name": "Marcus Lee", "company": "Northline"})
    assert db.update_lead(lead_id, status="contacted", score=82)
    lead = db.get_lead(lead_id)
    assert lead["status"] == "contacted"
    assert lead["score"] == 82
    assert lead["last_contacted_at"]

    stats = db.stats()
    assert stats["total"] == 1
    assert stats["by_status"]["contacted"] == 1
    assert stats["hot"] == 1


def test_invalid_status_rejected(tmp_path):
    fresh_db(tmp_path)
    lead_id, _ = db.upsert_lead({"name": "Test"})
    try:
        db.update_lead(lead_id, status="banana")
    except ValueError:
        pass
    else:
        raise AssertionError("Invalid status should raise")


def test_activities_and_delete(tmp_path):
    fresh_db(tmp_path)
    lead_id, _ = db.upsert_lead({"name": "Test Lead"})
    db.add_activity(lead_id, "note", "Called and left a voicemail.")
    activities = db.list_activities(lead_id)
    assert len(activities) == 1
    assert "voicemail" in activities[0]["content"]

    assert db.delete_lead(lead_id) is True
    assert db.get_lead(lead_id) is None
    assert db.list_activities(lead_id) == []


def test_list_leads_filters(tmp_path):
    fresh_db(tmp_path)
    db.upsert_lead({"name": "Alpha Dental", "company": "Alpha", "platform": "google"})
    db.upsert_lead({"name": "Beta Roofing", "company": "Beta", "platform": "facebook"})
    assert len(db.list_leads(platform="google")) == 1
    assert db.count_leads(query="roof") == 1


def test_export_csv(tmp_path):
    fresh_db(tmp_path)
    db.upsert_lead({"name": "Export Me", "email": "export@example.com"})
    text = db.export_rows()
    assert "Export Me" in text
    assert "export@example.com" in text
