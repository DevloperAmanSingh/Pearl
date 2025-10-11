from app.services.tasks import ingestion


def test_ingest_pull_request_task_invokes_processor(monkeypatch):
    payload = {
        "repository": {"full_name": "octocat/hello-world"},
        "pull_request": {"number": 42},
    }

    def fake_process(data):  # noqa: ANN001 - test helper
        assert data is payload
        return {
            "pull_request_id": 1,
            "repository": "octocat/hello-world",
            "pr_number": 42,
            "commit_count": 2,
            "file_count": 3,
        }

    monkeypatch.setattr(ingestion, "process_pull_request", fake_process)

    result = ingestion.ingest_pull_request.run(payload)

    assert result["status"] == "completed"
    assert result["commit_count"] == 2
    assert result["file_count"] == 3
