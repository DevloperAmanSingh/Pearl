from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def parse_github_timestamp(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    if value.endswith("Z"):
        value = value.replace("Z", "+00:00")
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def classify_file_size(additions: Optional[int], deletions: Optional[int]) -> str:
    additions = additions or 0
    deletions = deletions or 0
    total = additions + deletions
    if total <= 50:
        return "small"
    if total <= 200:
        return "medium"
    return "large"


def trim_patch(patch: Optional[str], limit: int = 4000) -> Optional[str]:
    if patch is None:
        return None
    if len(patch) <= limit:
        return patch
    return patch[:limit]
