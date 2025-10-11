from datetime import datetime, timedelta, timezone

import respx
from httpx import Response
from sqlmodel import select

from app.db.session import configure_engine, init_db, session_scope
from app.models.pr import PullRequest, PullRequestCommit, PullRequestFile
from app.services.github import auth as github_auth
from app.services.ingestion.pr_processor import process_pull_request


def setup_function() -> None:
    configure_engine("sqlite://")
    init_db()


@respx.mock
def test_process_pull_request_persists_metadata(monkeypatch) -> None:
    token = github_auth.GitHubInstallationToken(
        token="fake-token",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    monkeypatch.setattr(github_auth, "get_installation_token", lambda installation_id=None: token)

    repo = "octocat/hello-world"
    number = 42

    respx.get(f"https://api.github.com/repos/octocat/hello-world/pulls/{number}").mock(
        return_value=Response(
            200,
            json={
                "node_id": "PR_kwDOK",
                "title": "Add new feature",
                "state": "open",
                "head": {"sha": "abc123"},
                "base": {"sha": "def456"},
                "created_at": "2024-06-01T12:00:00Z",
                "updated_at": "2024-06-02T12:00:00Z",
            },
        )
    )

    respx.get(f"https://api.github.com/repos/octocat/hello-world/pulls/{number}/commits").mock(
        return_value=Response(
            200,
            json=[
                {
                    "sha": "abc123",
                    "commit": {
                        "message": "Initial commit",
                        "author": {"name": "Aman", "date": "2024-06-01T12:00:00Z"},
                    },
                }
            ],
        )
    )

    respx.get(f"https://api.github.com/repos/octocat/hello-world/pulls/{number}/files").mock(
        return_value=Response(
            200,
            json=[
                {
                    "filename": "app/main.py",
                    "status": "modified",
                    "additions": 10,
                    "deletions": 2,
                    "changes": 12,
                    "sha": "file-sha",
                    "blob_url": "https://example.com/blob",
                    "raw_url": "https://example.com/raw",
                    "contents_url": "https://example.com/contents",
                    "patch": "@@\n+print('hello')\n",
                }
            ],
        )
    )

    payload = {
        "repository": {"full_name": repo},
        "pull_request": {"number": number},
        "installation": {"id": 99},
    }

    result = process_pull_request(payload)

    assert result["repository"] == repo
    assert result["commit_count"] == 1
    assert result["file_count"] == 1

    with session_scope() as session:
        pr = session.exec(select(PullRequest)).one()
        assert pr.head_sha == "abc123"
        assert pr.base_sha == "def456"

        commit = session.exec(select(PullRequestCommit)).one()
        assert commit.message == "Initial commit"

        pr_file = session.exec(select(PullRequestFile)).one()
        assert pr_file.size_category == "small"
        assert pr_file.patch_excerpt.startswith("@@")
