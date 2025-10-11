from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class PullRequest(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    github_node_id: str = Field(index=True)
    repository_full_name: str = Field(index=True)
    number: int = Field(index=True)
    title: str
    state: str
    head_sha: str
    base_sha: str
    created_at: datetime
    updated_at: datetime
    last_synced_at: Optional[datetime] = None


class PullRequestCommit(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    pull_request_id: int = Field(foreign_key="pullrequest.id", index=True)
    sha: str = Field(index=True)
    message: str
    author_name: Optional[str] = None
    authored_date: Optional[datetime] = None


class PullRequestFile(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    pull_request_id: int = Field(foreign_key="pullrequest.id", index=True)
    filename: str
    status: str
    additions: int = 0
    deletions: int = 0
    changes: int = 0
    blob_sha: Optional[str] = None
    last_analyzed_commit_sha: Optional[str] = None
