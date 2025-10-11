from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Optional

import httpx
import jwt

from app.core.config import get_settings
from app.services.github.utils import parse_github_timestamp


@dataclass
class GitHubInstallationToken:
    token: str
    expires_at: datetime


_token_cache: Dict[int, GitHubInstallationToken] = {}
_private_key_cache: Optional[str] = None


def _load_private_key(private_key_path: str) -> str:
    global _private_key_cache
    if _private_key_cache is not None:
        return _private_key_cache

    path = Path(private_key_path)
    if not path.exists():
        raise FileNotFoundError(f"GitHub App private key not found at {private_key_path}")

    _private_key_cache = path.read_text()
    return _private_key_cache


def _generate_app_jwt(app_id: int, private_key: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "iat": int((now - timedelta(seconds=30)).timestamp()),
        "exp": int((now + timedelta(minutes=9)).timestamp()),
        "iss": app_id,
    }
    return jwt.encode(payload, private_key, algorithm="RS256")


def _request_installation_token(app_jwt: str, installation_id: int, api_base_url: str) -> GitHubInstallationToken:
    url = f"{api_base_url}/app/installations/{installation_id}/access_tokens"
    headers = {
        "Authorization": f"Bearer {app_jwt}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "pearl-ai-review",
    }
    with httpx.Client() as client:
        response = client.post(url, headers=headers, timeout=20)
    response.raise_for_status()
    data = response.json()
    expires_at = parse_github_timestamp(data.get("expires_at"))
    if not expires_at:
        raise RuntimeError("GitHub installation token response missing expires_at")
    return GitHubInstallationToken(token=data["token"], expires_at=expires_at)


def get_installation_token(installation_id: Optional[int] = None) -> GitHubInstallationToken:
    settings = get_settings()

    if not settings.github_app_id or not settings.github_app_private_key_path:
        raise RuntimeError("GitHub App ID and private key path must be configured")

    resolved_installation_id = installation_id or settings.github_app_installation_id
    if resolved_installation_id is None:
        raise RuntimeError("GitHub App installation ID must be configured")

    cached = _token_cache.get(resolved_installation_id)
    if cached and cached.expires_at - timedelta(minutes=1) > datetime.now(timezone.utc):
        return cached

    private_key = _load_private_key(settings.github_app_private_key_path)
    app_jwt = _generate_app_jwt(settings.github_app_id, private_key)
    token = _request_installation_token(app_jwt, resolved_installation_id, settings.github_api_base_url)
    _token_cache[resolved_installation_id] = token
    return token
