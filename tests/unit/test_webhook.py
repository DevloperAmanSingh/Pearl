from fastapi.testclient import TestClient

from app.api import routes_review
from app.main import app


client = TestClient(app)


def test_pull_request_event_enqueues(monkeypatch):
    captured = {}

    def fake_enqueue(payload):
        captured["payload"] = payload

    monkeypatch.setattr(routes_review, "enqueue_pull_request_ingestion", fake_enqueue)

    payload = {
        "action": "opened",
        "pull_request": {"number": 42},
        "repository": {"full_name": "octocat/hello-world"},
    }

    response = client.post(
        "/webhooks/github",
        json=payload,
        headers={
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": "abc-123",
        },
    )

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert captured["payload"]["delivery_id"] == "abc-123"


def test_non_pull_request_event_ignored():
    response = client.post(
        "/webhooks/github",
        json={},
        headers={"X-GitHub-Event": "push"},
    )

    assert response.status_code == 202
    assert response.json()["status"] == "ignored"
