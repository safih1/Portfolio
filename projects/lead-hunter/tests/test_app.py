from __future__ import annotations

import db
from app import create_app


def make_client(tmp_path):
    app = create_app(tmp_path / "app.db")
    app.config.update(TESTING=True)
    return app.test_client()


def test_pages_render(tmp_path):
    client = make_client(tmp_path)
    for path in ("/", "/leads", "/tools"):
        response = client.get(path)
        assert response.status_code == 200, path


def test_health(tmp_path):
    response = make_client(tmp_path).get("/api/health")
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["leads"] == 0


def test_create_update_and_export(tmp_path):
    client = make_client(tmp_path)
    response = client.post(
        "/leads/new",
        data={
            "name": "Amelia Hart",
            "company": "Bright Smile",
            "email": "amelia@example.com",
            "platform": "facebook",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    leads = db.list_leads()
    assert len(leads) == 1

    lead_id = leads[0]["id"]
    detail = client.get(f"/leads/{lead_id}")
    assert detail.status_code == 200
    assert b"Amelia Hart" in detail.data
    assert b"Lead assistant" in detail.data

    response = client.post(
        f"/leads/{lead_id}/update", data={"status": "contacted"}, follow_redirects=False
    )
    assert response.status_code == 302
    assert db.get_lead(lead_id)["status"] == "contacted"

    export = client.get("/export.csv")
    assert export.status_code == 200
    assert b"Amelia Hart" in export.data


def test_lead_chat_reply(tmp_path, monkeypatch):
    import ai

    client = make_client(tmp_path)
    client.post(
        "/leads/new",
        data={"name": "Amelia Hart", "company": "Bright Smile", "platform": "facebook"},
    )
    lead_id = db.list_leads()[0]["id"]

    seen = {}

    def fake_chat(lead, messages):
        seen["lead"] = lead
        seen["messages"] = messages
        return "Lead with the missed-call angle."

    monkeypatch.setattr(ai, "chat_about_lead", fake_chat)
    response = client.post(
        f"/leads/{lead_id}/chat",
        json={"messages": [{"role": "user", "content": "What angle should I use?"}]},
    )

    assert response.status_code == 200
    assert response.get_json()["reply"] == "Lead with the missed-call angle."
    assert seen["lead"]["name"] == "Amelia Hart"
    assert seen["messages"][-1] == {
        "role": "user",
        "content": "What angle should I use?",
    }


def test_lead_chat_validation(tmp_path):
    client = make_client(tmp_path)
    client.post("/leads/new", data={"name": "Amelia Hart"})
    lead_id = db.list_leads()[0]["id"]

    assert client.post(f"/leads/{lead_id}/chat", json={}).status_code == 400
    assert (
        client.post(f"/leads/{lead_id}/chat", json={"messages": []}).status_code == 400
    )
    assert (
        client.post(
            f"/leads/{lead_id}/chat",
            json={"messages": [{"role": "assistant", "content": "Hello"}]},
        ).status_code
        == 400
    )
    assert (
        client.post(
            f"/leads/{lead_id}/chat",
            json={"messages": [{"role": ["user"], "content": "Hello"}]},
        ).status_code
        == 400
    )
    assert (
        client.post(
            f"/leads/{lead_id}/chat",
            json={"messages": [{"role": "user", "content": "   "}]},
        ).status_code
        == 400
    )
    assert client.post("/leads/999/chat", json={"messages": []}).status_code == 404


def test_facebook_webhook_verification(tmp_path, monkeypatch):
    import config

    monkeypatch.setattr(config, "FACEBOOK_VERIFY_TOKEN", "verify-me")
    client = make_client(tmp_path)
    response = client.get(
        "/webhooks/facebook",
        query_string={
            "hub.mode": "subscribe",
            "hub.verify_token": "verify-me",
            "hub.challenge": "12345",
        },
    )
    assert response.status_code == 200
    assert response.get_data(as_text=True) == "12345"
    assert client.get("/webhooks/facebook").status_code == 403


def test_404(tmp_path):
    assert make_client(tmp_path).get("/leads/999").status_code == 404
