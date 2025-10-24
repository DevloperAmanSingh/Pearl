from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List

import httpx
from sqlmodel import select

from functools import lru_cache

from app.core.config import get_settings
from app.db.session import session_scope
from app.models.pr import PullRequest, PullRequestFile
from app.models.review import PullRequestAnalysisRun, PullRequestFinding
from app.services.agents.base import AgentContext
from app.services.agents.review_agent import ReviewAgent
from app.services.analysis.llm_client import OpenAILLMClient
from app.services.analysis.prompt_builder import ReviewPromptBuilder
from app.services.analysis.raw_logger import RawTraceWriter
from app.services.chunking.ast_chunker import ASTChunker
from app.services.chunking.chunk_selector import ChunkSelector
from app.services.chunking.patch_chunker import PatchChunker
from app.services.chunking.utils import extract_changed_lines, language_from_filename
from app.services.github.auth import get_installation_token
from app.services.github.client import get_github_client

logger = logging.getLogger(__name__)

PR_BODY_CHAR_LIMIT = 2000
PR_SUMMARY_CHAR_LIMIT = 400


def _normalize_newlines(value: str) -> str:
    return "\n".join(line.rstrip() for line in value.splitlines())


def _truncate_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    truncated = value[:limit].rsplit(" ", 1)[0].rstrip()
    if not truncated:
        truncated = value[:limit].rstrip()
    return f"{truncated}…"


def _prepare_pr_body(raw_body: str | None) -> str | None:
    if not raw_body:
        return None
    cleaned = raw_body.strip()
    if not cleaned:
        return None
    normalized = _normalize_newlines(cleaned)
    if len(normalized) <= PR_BODY_CHAR_LIMIT:
        return normalized
    return _truncate_text(normalized, PR_BODY_CHAR_LIMIT)


def _build_pr_summary(title: str | None, raw_body: str | None) -> str | None:
    segments: List[str] = []
    title = (title or "").strip()
    if title:
        segments.append(title)
    if raw_body:
        compact_body = " ".join(raw_body.split())
        if compact_body:
            segments.append(compact_body)
    if not segments:
        return None
    combined = " — ".join(segments) if len(segments) > 1 else segments[0]
    return _truncate_text(combined, PR_SUMMARY_CHAR_LIMIT)


class ReviewEngine:
    def __init__(self, agent: ReviewAgent | None = None, trace_writer: RawTraceWriter | None = None) -> None:
        if agent is None:
            ast_chunker = ASTChunker()
            patch_chunker = PatchChunker()
            chunk_selector = ChunkSelector(ast_chunker, patch_chunker)
            prompt_builder = ReviewPromptBuilder()
            llm_client = OpenAILLMClient()
            agent = ReviewAgent(chunk_selector, prompt_builder, llm_client)
        self._agent = agent
        self._trace_writer = trace_writer or RawTraceWriter()

    def analyze(self, pull_request_id: int) -> Dict[str, int]:
        with session_scope() as session:
            pull_request = session.get(PullRequest, pull_request_id)
            if not pull_request:
                raise ValueError(f"Pull request {pull_request_id} not found")

            files = session.exec(
                select(PullRequestFile).where(PullRequestFile.pull_request_id == pull_request_id)
            ).all()

            analysis_run = PullRequestAnalysisRun(
                pull_request_id=pull_request_id,
                model=get_settings().openai_model,
                status="running",
                total_files=len(files),
            )
            session.add(analysis_run)
            session.flush()

            try:
                token_info = get_installation_token()
                with get_github_client(token_info.token) as github:
                    pr_details: Dict[str, Any] | None = None
                    pr_body_excerpt: str | None = None
                    pr_summary: str | None = None
                    pr_title = pull_request.title
                    try:
                        pr_details = github.get_pull_request(pull_request.repository_full_name, pull_request.number)
                    except httpx.HTTPStatusError as exc:
                        logger.warning(
                            "Failed to retrieve PR metadata",
                            extra={
                                "pull_request_id": pull_request.id,
                                "status": exc.response.status_code,
                            },
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "Failed to retrieve PR metadata",
                            extra={
                                "pull_request_id": pull_request.id,
                                "error": str(exc),
                            },
                        )
                    else:
                        pr_title = pr_details.get("title") or pr_title
                        pr_body_excerpt = _prepare_pr_body(pr_details.get("body"))
                        pr_summary = _build_pr_summary(pr_title, pr_details.get("body"))

                    findings, processed_files = self._process_files(
                        session,
                        analysis_run,
                        pull_request,
                        files,
                        github,
                        pr_title,
                        pr_body_excerpt,
                        pr_summary,
                    )
            except Exception as exc:  # noqa: BLE001 - we need to capture and persist failure state
                logger.exception("Analysis failed", extra={"pull_request_id": pull_request_id})
                analysis_run.status = "failed"
                session.add(analysis_run)
                session.commit()
                raise

            analysis_run.status = "completed"
            analysis_run.completed_at = datetime.utcnow()
            analysis_run.total_findings = len(findings)
            analysis_run.total_files = processed_files
            session.add(analysis_run)
            session.commit()

            return {
                "files_processed": processed_files,
                "findings": len(findings),
                "analysis_run_id": analysis_run.id,
            }

    def _process_files(
        self,
        session,
        analysis_run,
        pull_request,
        files,
        github_client,
        pr_title: str,
        pr_body: str | None,
        pr_summary: str | None,
    ) -> tuple[List[PullRequestFinding], int]:
        findings: List[PullRequestFinding] = []
        processed_files = 0

        for file_record in files:
            if file_record.status in {"removed", "deleted"}:
                logger.debug(
                    "Skipping removed file from analysis",
                    extra={"file": file_record.filename, "pull_request_id": pull_request.id},
                )
                continue

            language = language_from_filename(file_record.filename)
            patch = file_record.patch_excerpt
            changed_lines = extract_changed_lines(patch)

            try:
                source_code = github_client.get_file_contents(
                    pull_request.repository_full_name,
                    file_record.filename,
                    pull_request.head_sha,
                )
            except httpx.HTTPStatusError as exc:
                logger.warning(
                    "Failed to fetch file contents",
                    extra={"file": file_record.filename, "status": exc.response.status_code},
                )
                continue

            processed_files += 1
            context = AgentContext(
                pull_request_id=pull_request.id,
                repository_full_name=pull_request.repository_full_name,
                pr_number=pull_request.number,
                head_sha=pull_request.head_sha,
                base_sha=pull_request.base_sha,
                pull_request_title=pr_title,
                pull_request_body=pr_body,
                pull_request_summary=pr_summary,
                file_path=file_record.filename,
                diff_hunk=patch,
                language=language,
                source_code=source_code,
                patch=patch,
                changed_lines=changed_lines,
                metadata={"pull_request_file_id": file_record.id},
            )

            agent_result = self._agent.run(context)
            for finding in agent_result.findings:
                finding_record = PullRequestFinding(
                    analysis_run_id=analysis_run.id,
                    pull_request_id=pull_request.id,
                    pull_request_file_id=file_record.id,
                    file_path=finding.file_path or file_record.filename,
                    severity=finding.severity,
                    title=finding.title,
                    summary=finding.summary,
                    start_line=finding.start_line,
                    end_line=finding.end_line,
                    raw_response=finding.raw_response,
                )
                session.add(finding_record)
                findings.append(finding_record)

            if agent_result.findings:
                logger.info(
                    "Agent findings",
                    extra={
                        "pull_request_id": pull_request.id,
                        "file": file_record.filename,
                        "finding_count": len(agent_result.findings),
                        "titles": [finding.title for finding in agent_result.findings],
                        "raw_llm_response": agent_result.diagnostics.get("chunks"),
                    },
                )

            diagnostics = agent_result.diagnostics.get("chunks")
            if diagnostics:
                try:
                    self._trace_writer.write(
                        repository=pull_request.repository_full_name,
                        pr_number=pull_request.number,
                        head_sha=pull_request.head_sha,
                        file_path=file_record.filename,
                        diagnostics=diagnostics,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Failed to write raw LLM trace",
                        extra={
                            "pull_request_id": pull_request.id,
                            "file": file_record.filename,
                            "error": str(exc),
                        },
                    )

            file_record.last_analyzed_commit_sha = pull_request.head_sha
            session.add(file_record)

        return findings, processed_files


@lru_cache(maxsize=1)
def get_review_engine() -> ReviewEngine:
    return ReviewEngine()
