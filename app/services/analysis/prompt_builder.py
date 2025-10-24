from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from app.services.agents.base import AgentContext
from app.services.chunking.base import CodeChunk

HUNK_HEADER_RE = re.compile(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


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
            "You are an experienced senior software engineer performing a rigorous code review.\n"
            "Focus on defects affecting correctness, reliability, security, and maintainability; ignore style-only concerns unless they mask a bug.\n"
            f"Respond ONLY with valid JSON shaped exactly as {{\"findings\": [{{\"title\": str, \"summary\": str, \"severity\": \"high\"|\"medium\"|\"low\", \"start_line\": int, \"end_line\": int}}]}} with at most {self._max_findings} findings.\n"
            "Use severity \"high\" for definite bugs or security issues, \"medium\" for risky or fragile logic, and \"low\" for smaller but concrete issues.\n"
            "start_line and end_line must reference NEW-code line numbers from the diff and should be the narrowest range covering the problem.\n"
            "Always use the annotated line numbers shown in the diff (e.g. \"123:\") when deciding start_line and end_line.\n"
            "If there are no actionable issues, respond exactly with {\"findings\": []}.\n"
            "Do not add commentary, markdown fences, or any other text outside the JSON object."
        )

        full_patch = chunk.diff_hunk or context.patch or ""
        formatted_changes, new_line_ranges = _format_patch_for_prompt(full_patch)
        changed_lines = ", ".join(str(line) for line in (context.changed_lines or [])) or "unknown"

        sections: List[str] = []

        if include_pr_metadata:
            pr_context_lines: List[str] = [
                f"Repository: {context.repository_full_name}",
                f"Pull request: #{context.pr_number}",
                f"Head SHA: {context.head_sha}",
                f"Base SHA: {context.base_sha}",
            ]
            if context.pull_request_title:
                pr_context_lines.append(f"Title: {context.pull_request_title}")
            if context.pull_request_summary:
                pr_context_lines.append(f"Summary: {context.pull_request_summary}")
            sections.append("## Pull Request Context\n" + "\n".join(pr_context_lines))
            if context.pull_request_body:
                sections.append("### PR Description\n" + context.pull_request_body)

        file_context_lines = [
            f"File path: {chunk.file_path}",
            f"Language: {context.language or 'unknown'}",
            f"Chunk type: {chunk.metadata.get('chunk_type')}",
            f"Changed lines: {changed_lines}",
        ]
        sections.append("## File Context\n" + "\n".join(file_context_lines))

        instruction_lines = [
            "- Review only the diff hunks provided below.",
            "- Flag issues that would cause incorrect behavior, security vulnerabilities, data loss, crashes, or significant maintainability risks.",
            "- Provide concise, actionable reasoning in each summary and mention fixes when obvious.",
            "- Omit findings when the change is acceptable and introduces no issues.",
        ]
        sections.append("## Review Instructions\n" + "\n".join(instruction_lines))

        if formatted_changes:
            sections.append("## Changes\n" + formatted_changes)
        else:
            sections.append("## Changes\n(no diff available)")

        language_hint = (chunk.metadata.get("language") if chunk.metadata else None) or context.language or ""
        code_body = ""
        if context.source_code and chunk.start_line and chunk.end_line:
            source_lines = context.source_code.splitlines()
            start_idx = max(chunk.start_line - 1, 0)
            end_idx = min(chunk.end_line, len(source_lines))
            code_body = "\n".join(source_lines[start_idx:end_idx])
        if not code_body:
            code_body = chunk.content or ""
        if code_body.strip():
            sections.append(f"## Current File Snippet\n```{language_hint}\n{code_body}\n```")
        else:
            sections.append("## Current File Snippet\n(no source excerpt available)")

        user_content = "\n\n".join(section for section in sections if section).strip()

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
                "pull_request_body": context.pull_request_body,
                "pull_request_title": context.pull_request_title,
                "pull_request_summary": context.pull_request_summary,
                "changed_lines": context.changed_lines,
                "new_line_ranges": new_line_ranges,
            },
        )


def _format_patch_for_prompt(patch: str) -> Tuple[Optional[str], List[Tuple[int, int]]]:
    if not patch:
        return None, []

    hunks = _split_patch(patch)
    if not hunks:
        return None, []

    sections: List[str] = []
    ranges: List[Tuple[int, int]] = []

    for hunk in hunks:
        header, new_hunk, old_hunk, line_range = _parse_patch_hunk(hunk)
        if header is None:
            continue
        ranges.append(line_range)
        sections.extend(
            [
                header,
                "---new_hunk---",
                "```",
                new_hunk if new_hunk else "(no new lines)",
                "```",
                "",
                "---old_hunk---",
                "```",
                old_hunk if old_hunk else "(no old lines)",
                "```",
                "",
            ]
        )

    if not sections:
        return None, []

    return "\n".join(sections).strip(), ranges


def _split_patch(patch: str) -> List[str]:
    lines = patch.splitlines()
    hunks: List[List[str]] = []
    current: List[str] = []
    for line in lines:
        if HUNK_HEADER_RE.match(line):
            if current:
                hunks.append(current)
            current = [line]
        else:
            if current:
                current.append(line)
    if current:
        hunks.append(current)
    return ["\n".join(hunk) for hunk in hunks]


def _parse_patch_hunk(hunk: str) -> Tuple[Optional[str], str, str, Tuple[int, int]]:
    lines = hunk.splitlines()
    if not lines:
        return None, "", "", (0, 0)

    header = lines[0]
    match = HUNK_HEADER_RE.match(header)
    if not match:
        return None, "", "", (0, 0)

    new_start = int(match.group(3))
    new_count = int(match.group(4) or "0")

    new_line_ptr = new_start

    body = lines[1:]
    removal_only = not any(line.startswith("+") and not line.startswith("+++") for line in body)
    skip_start = 3
    skip_end = 3

    new_hunk_lines: List[str] = []
    old_hunk_lines: List[str] = []

    for idx, line in enumerate(body):
        if line.startswith("+") and not line.startswith("+++"):
            text = line[1:]
            new_hunk_lines.append(f"{new_line_ptr}: {text}")
            new_line_ptr += 1
        elif line.startswith("-") and not line.startswith("---"):
            text = line[1:]
            old_hunk_lines.append(text)
        else:
            text = line[1:] if line.startswith(" ") else line
            old_hunk_lines.append(text)
            include_number = removal_only or (
                idx >= skip_start and idx < len(body) - skip_end
            )
            prefix = f"{new_line_ptr}: " if include_number and text != "" else ""
            new_hunk_lines.append(f"{prefix}{text}")
            if not line.startswith("\\"):
                new_line_ptr += 1

    if new_count == 0:
        line_range = (new_start, new_start)
    else:
        line_range = (new_start, new_start + max(new_count - 1, 0))

    new_hunk = "\n".join(new_hunk_lines).strip("\n")
    old_hunk = "\n".join(old_hunk_lines).strip("\n")

    return header, new_hunk, old_hunk, line_range
