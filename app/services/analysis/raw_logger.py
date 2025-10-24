from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable

logger = logging.getLogger(__name__)


class RawTraceWriter:
    def __init__(self, base_path: str | Path = "raw") -> None:
        self._base_path = Path(base_path)

    def write(self, *, repository: str, pr_number: int, head_sha: str, file_path: str, diagnostics: Iterable[Dict[str, Any]]) -> Path:
        repo_dir = repository.replace("/", "__")
        target_dir = self._base_path / repo_dir / f"pr-{pr_number}" / f"commit-{head_sha}"
        target_dir.mkdir(parents=True, exist_ok=True)

        safe_file = file_path.replace("/", "__")
        output_path = target_dir / f"{safe_file}.json"

        payload = {
            "repository": repository,
            "pull_request_number": pr_number,
            "head_sha": head_sha,
            "file_path": file_path,
            "chunks": list(diagnostics),
        }

        with output_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

        logger.debug("Wrote raw LLM trace", extra={"path": str(output_path)})
        return output_path
