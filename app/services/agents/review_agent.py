from __future__ import annotations

import logging
from typing import Iterable, Protocol

from app.services.agents.base import AgentContext, AgentFinding, AgentResult
from app.services.analysis.prompt_builder import PromptPayload

logger = logging.getLogger(__name__)


class Chunk(Protocol):
    """
    Minimal protocol for a code chunk produced by the chunking layer.
    """

    file_path: str
    content: str
    diff_hunk: str | None
    start_line: int | None
    end_line: int | None
    metadata: dict


class Chunker(Protocol):
    def generate_chunks(self, context: AgentContext) -> Iterable[Chunk]:
        ...


class PromptBuilder(Protocol):
    def build_prompt(self, context: AgentContext, chunk: Chunk) -> PromptPayload:
        ...


class LLMClient(Protocol):
    def review_chunk(self, prompt: PromptPayload) -> dict:
        ...


class ReviewAgent:
    """
    Agent responsible for turning diff chunks into review findings via LLM prompts.
    """

    def __init__(self, chunker: Chunker, prompt_builder: PromptBuilder, llm_client: LLMClient) -> None:
        self._chunker = chunker
        self._prompt_builder = prompt_builder
        self._llm = llm_client

    def run(self, context: AgentContext) -> AgentResult:
        findings: list[AgentFinding] = []
        diagnostics: list[dict] = []

        first_chunk = True
        for chunk in self._chunker.generate_chunks(context):
            prompt = self._prompt_builder.build_prompt(context, chunk, include_pr_metadata=first_chunk)
            logger.debug(
                "Submitting chunk to LLM",
                extra={
                    "file_path": chunk.file_path,
                    "start_line": getattr(chunk, "start_line", None),
                    "end_line": getattr(chunk, "end_line", None),
                },
            )
            response = self._llm.review_chunk(prompt)
            diagnostics.append(
                {
                    "file_path": chunk.file_path,
                    "prompt": prompt.messages,
                    "prompt_metadata": prompt.metadata,
                    "response": response,
                    "chunk": {
                        "start_line": getattr(chunk, "start_line", None),
                        "end_line": getattr(chunk, "end_line", None),
                        "metadata": chunk.metadata,
                    },
                }
            )

            chunk_findings = self._normalize_findings(context, chunk, response, prompt.metadata)
            findings.extend(chunk_findings)
            first_chunk = False

        return AgentResult(agent_name=self.__class__.__name__, findings=findings, diagnostics={"chunks": diagnostics})

    def _normalize_findings(
        self,
        context: AgentContext,
        chunk: Chunk,
        response: dict,
        prompt_metadata: dict | None = None,
    ) -> list[AgentFinding]:
        findings: list[AgentFinding] = []
        items = response.get("findings", [])
        if not isinstance(items, list):
            logger.debug("LLM response missing findings list", extra={"file_path": chunk.file_path})
            return findings

        line_ranges = []
        if prompt_metadata and isinstance(prompt_metadata, dict):
            line_ranges = prompt_metadata.get("new_line_ranges") or []
            if not isinstance(line_ranges, list):
                line_ranges = []

        for item in items:
            if not isinstance(item, dict):
                continue
            title = item.get("title")
            summary = item.get("summary")
            severity = item.get("severity", "medium")
            if not title or not summary:
                continue
            severity = str(severity).lower()
            if severity not in {"low", "medium", "high"}:
                severity = "medium"

            start_line = item.get("start_line")
            end_line = item.get("end_line") or start_line

            mapped_start, mapped_end, note = _map_line_range(
                start_line if isinstance(start_line, int) else None,
                end_line if isinstance(end_line, int) else None,
                line_ranges,
                default_start=getattr(chunk, "start_line", None),
                default_end=getattr(chunk, "end_line", None),
            )

            if mapped_start is None:
                continue

            if note:
                summary = f"{note}\n\n{summary}"

            findings.append(
                AgentFinding(
                    title=title,
                    summary=summary,
                    severity=severity,
                    file_path=context.file_path or chunk.file_path,
                    start_line=mapped_start,
                    end_line=mapped_end,
                    raw_response=item,
                )
            )

        return findings


def _map_line_range(
    start_line: int | None,
    end_line: int | None,
    patches: list,
    *,
    default_start: int | None,
    default_end: int | None,
) -> tuple[int | None, int | None, str | None]:
    original_start = start_line
    original_end = end_line

    if start_line is None or not isinstance(start_line, int):
        start_line = default_start
    if end_line is None or not isinstance(end_line, int):
        end_line = start_line if start_line is not None else default_end

    if start_line is None:
        return default_start, default_end, None
    if end_line is None:
        end_line = start_line
    if end_line < start_line:
        start_line, end_line = end_line, start_line

    normalized_patches: list[tuple[int, int]] = []
    for patch in patches:
        if isinstance(patch, (list, tuple)) and len(patch) == 2:
            patch_start, patch_end = patch
            if isinstance(patch_start, int) and isinstance(patch_end, int):
                normalized_patches.append((patch_start, patch_end))

    if not normalized_patches:
        return start_line, end_line, None

    for patch_start, patch_end in normalized_patches:
        if patch_start <= start_line and end_line <= patch_end:
            return start_line, end_line, None

    best_patch: tuple[int, int] | None = None
    best_intersection = 0
    for patch_start, patch_end in normalized_patches:
        intersection_start = max(start_line, patch_start)
        intersection_end = min(end_line, patch_end)
        intersection = max(0, intersection_end - intersection_start + 1)
        if intersection > best_intersection:
            best_intersection = intersection
            best_patch = (patch_start, patch_end)

    if best_patch:
        mapped_start, mapped_end = best_patch
        note = (
            f"> Note: Comment mapped to diff hunk lines [{mapped_start}-{mapped_end}] "
            f"(original request {original_start}-{original_end})."
        )
        return mapped_start, mapped_end, note

    fallback_start, fallback_end = normalized_patches[0]
    note = (
        f"> Note: Comment outside diff; defaulted to hunk [{fallback_start}-{fallback_end}] "
        f"(original request {original_start}-{original_end})."
    )
    return fallback_start, fallback_end, note
