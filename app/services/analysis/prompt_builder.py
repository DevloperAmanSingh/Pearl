from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from app.services.agents.base import AgentContext
from app.services.chunking.base import CodeChunk
from app.services.chunking.utils import compact_diff


@dataclass(slots=True)
class PromptPayload:
    messages: List[Dict[str, str]]
    max_output_tokens: int = 800
    temperature: float = 0.1
    metadata: Dict[str, object] = field(default_factory=dict)


class ReviewPromptBuilder:
    def __init__(self, max_findings: int = 3) -> None:
        self._max_findings = max_findings

    def build_prompt(self, context: AgentContext, chunk: CodeChunk, *, include_pr_metadata: bool) -> PromptPayload:
        system_message = (
            "Role: senior engineer reviewing code.\n"
            "Focus: correctness, security, maintainability.\n"
            f"Respond with a single JSON object {{\"findings\": [{{\"title\",\"summary\",\"severity\",\"start_line\",\"end_line\"}}]}} (max {self._max_findings}).\n"
            "Severity must be one of low|medium|high. If there are no issues respond exactly with {\"findings\": []}.\n"
            "Return only JSON. Do not add prose, markdown, or code fences."
        )

        full_patch = chunk.diff_hunk or context.patch
        diff_view, truncated = compact_diff(full_patch)
        changed_lines = ", ".join(str(line) for line in (context.changed_lines or [])) or "unknown"

        header_lines: List[str] = []
        if include_pr_metadata:
            header_lines.extend(
                [
                    f"Repository: {context.repository_full_name}",
                    f"Pull request: #{context.pr_number}",
                    f"Head SHA: {context.head_sha}",
                    f"Base SHA: {context.base_sha}",
                ]
            )

        header_lines.extend(
            [
                f"File: {chunk.file_path}",
                f"Language: {context.language or 'unknown'}",
                f"Chunk type: {chunk.metadata.get('chunk_type')}",
                f"Changed lines: {changed_lines}",
            ]
        )

        sections = [
            "\n".join(header_lines),
            "--- Diff ---",
            diff_view or "(no diff available)",
            "--- Code ---",
            chunk.content,
        ]

        if truncated and full_patch:
            sections.extend(
                [
                    "--- Full Diff ---",
                    full_patch,
                ]
            )

        user_content = "\n".join(sections).strip()

        return PromptPayload(
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_content},
            ],
            metadata={
                "file_path": chunk.file_path,
                "chunk_type": chunk.metadata.get("chunk_type"),
                "language": context.language,
                "included_pr_metadata": include_pr_metadata,
            },
        )
