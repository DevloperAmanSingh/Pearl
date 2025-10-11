from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Iterable

from sqlmodel import delete, select
from app.db.session import session_scope
from app.models.pr import PullRequest, PullRequestCommit, PullRequestFile
from app.services.github.auth import get_installation_token
from app.services.github.client import get_github_client
from app.services.github.utils import classify_file_size, parse_github_timestamp, trim_patch

logger = logging.getLogger(__name__)


def _upsert_pull_request(session, repo_full_name: str, pr_number: int, pr_data: Dict[str, Any]) -> PullRequest:
    stmt = select(PullRequest).where(
        PullRequest.repository_full_name == repo_full_name,
        PullRequest.number == pr_number,
    )
    pr = session.exec(stmt).one_or_none()

    created_at = parse_github_timestamp(pr_data.get("created_at")) or datetime.now(timezone.utc)
    updated_at = parse_github_timestamp(pr_data.get("updated_at")) or created_at
    head_sha = (pr_data.get("head") or {}).get("sha")
    base_sha = (pr_data.get("base") or {}).get("sha")

    if pr is None:
        pr = PullRequest(
            github_node_id=pr_data.get("node_id", ""),
            repository_full_name=repo_full_name,
            number=pr_number,
            title=pr_data.get("title", ""),
            state=pr_data.get("state", "open"),
            head_sha=head_sha or "",
            base_sha=base_sha or "",
            created_at=created_at,
            updated_at=updated_at,
            last_synced_at=datetime.now(timezone.utc),
        )
    else:
        pr.github_node_id = pr_data.get("node_id", pr.github_node_id)
        pr.title = pr_data.get("title", pr.title)
        pr.state = pr_data.get("state", pr.state)
        pr.head_sha = head_sha or pr.head_sha
        pr.base_sha = base_sha or pr.base_sha
        pr.updated_at = updated_at
        pr.last_synced_at = datetime.now(timezone.utc)

    session.add(pr)
    session.flush()
    return pr


def _replace_commits(session, pr_id: int, commits: Iterable[Dict[str, Any]]) -> int:
    session.exec(delete(PullRequestCommit).where(PullRequestCommit.pull_request_id == pr_id))
    count = 0
    for commit_data in commits:
        commit = commit_data.get("commit", {})
        author = commit.get("author") or {}
        session.add(
            PullRequestCommit(
                pull_request_id=pr_id,
                sha=commit_data.get("sha", ""),
                message=commit.get("message", ""),
                author_name=author.get("name"),
                authored_date=parse_github_timestamp(author.get("date")),
            )
        )
        count += 1
    return count


def _replace_files(session, pr_id: int, files: Iterable[Dict[str, Any]]) -> int:
    session.exec(delete(PullRequestFile).where(PullRequestFile.pull_request_id == pr_id))
    count = 0
    for file_data in files:
        additions = file_data.get("additions")
        deletions = file_data.get("deletions")
        session.add(
            PullRequestFile(
                pull_request_id=pr_id,
                filename=file_data.get("filename", ""),
                status=file_data.get("status", "modified"),
                additions=additions or 0,
                deletions=deletions or 0,
                changes=file_data.get("changes") or (additions or 0) + (deletions or 0),
                blob_sha=file_data.get("sha"),
                blob_url=file_data.get("blob_url"),
                raw_url=file_data.get("raw_url"),
                contents_url=file_data.get("contents_url"),
                patch_excerpt=trim_patch(file_data.get("patch")),
                size_category=classify_file_size(additions, deletions),
                last_analyzed_commit_sha=None,
            )
        )
        count += 1
    return count


def process_pull_request(payload: Dict[str, Any]) -> Dict[str, Any]:
    repository = payload.get("repository") or {}
    pull_request = payload.get("pull_request") or {}
    repo_full_name = repository.get("full_name")
    pr_number = pull_request.get("number")

    if not repo_full_name or pr_number is None:
        raise ValueError("Payload missing repository full_name or pull_request number")

    installation = payload.get("installation") or {}
    installation_id = installation.get("id")

    token_info = get_installation_token(installation_id)
    with get_github_client(token_info.token) as github:
        pr_data = github.get_pull_request(repo_full_name, pr_number)
        commits = list(github.list_pull_request_commits(repo_full_name, pr_number))
        files = list(github.list_pull_request_files(repo_full_name, pr_number))

    with session_scope() as session:
        pr_record = _upsert_pull_request(session, repo_full_name, pr_number, pr_data)
        commit_count = _replace_commits(session, pr_record.id, commits)
        file_count = _replace_files(session, pr_record.id, files)
        session.refresh(pr_record)

    logger.info(
        "Pull request synced",
        extra={
            "repository": repo_full_name,
            "pr_number": pr_number,
            "commit_count": commit_count,
            "file_count": file_count,
        },
    )

    return {
        "pull_request_id": pr_record.id,
        "repository": repo_full_name,
        "pr_number": pr_number,
        "commit_count": commit_count,
        "file_count": file_count,
    }
