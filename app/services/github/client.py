from __future__ import annotations

from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

import httpx

from app.core.config import get_settings

DEFAULT_TIMEOUT = 20


class GitHubClient:
    def __init__(self, token: str, base_url: Optional[str] = None, timeout: int = DEFAULT_TIMEOUT) -> None:
        settings = get_settings()
        self._client = httpx.Client(
            base_url=base_url or settings.github_api_base_url,
            headers={
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "pearl-ai-review",
            },
            timeout=timeout,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "GitHubClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001, ANN201
        self.close()

    @staticmethod
    def _split_repo(repo_full_name: str) -> Tuple[str, str]:
        owner, repo = repo_full_name.split("/", 1)
        return owner, repo

    def _paginate(self, url: str, params: Optional[Dict[str, Any]] = None) -> Iterator[Dict[str, Any]]:
        params = params or {}
        page = 1
        while True:
            merged_params = {"per_page": 100, "page": page, **params}
            response = self._client.get(url, params=merged_params)
            response.raise_for_status()
            items: List[Dict[str, Any]] = response.json()
            if not items:
                break
            for item in items:
                yield item
            if "next" not in response.links:
                break
            page += 1

    def get_pull_request(self, repo_full_name: str, number: int) -> Dict[str, Any]:
        owner, repo = self._split_repo(repo_full_name)
        response = self._client.get(f"/repos/{owner}/{repo}/pulls/{number}")
        response.raise_for_status()
        return response.json()

    def list_pull_request_commits(self, repo_full_name: str, number: int) -> Iterable[Dict[str, Any]]:
        owner, repo = self._split_repo(repo_full_name)
        endpoint = f"/repos/{owner}/{repo}/pulls/{number}/commits"
        return self._paginate(endpoint)

    def list_pull_request_files(self, repo_full_name: str, number: int) -> Iterable[Dict[str, Any]]:
        owner, repo = self._split_repo(repo_full_name)
        endpoint = f"/repos/{owner}/{repo}/pulls/{number}/files"
        return self._paginate(endpoint)


def get_github_client(token: str) -> GitHubClient:
    return GitHubClient(token=token)
