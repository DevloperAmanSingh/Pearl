# AI Code Review – Phase 1 PRD

## Overview
Build an automated pull-request reviewer that ingests GitHub events, analyzes code changes with AST-aware chunking, and posts structured review comments backed by OpenAI models. Phase 1 targets reliability on small-to-medium PRs (<1k changed LOC) with a latency budget under five minutes.

## Goals
- Deliver actionable review comments with ≥80% human-rated relevance.
- Maintain end-to-end latency ≤5 minutes for 95% of PRs in scope.
- Achieve <5% failure rate across ingestion, processing, and feedback stages.

## Out of Scope
- Automatic code fixes or patch suggestions.
- Reviewer assignment logic or CI gating.
- Support for non-GitHub VCS platforms.
- Multi-LLM routing or customer-specific prompt tuning.

## Architecture Overview
- GitHub App webhook triggers ingestion service.
- PR metadata and diff snapshots persisted in PostgreSQL.
- Processing pipeline executed via Celery workers (Redis/SQS broker pluggable).
- AST-aware chunking (tree-sitter) with semantic embeddings for large contexts.
- Prompt builder assembles concise, file-specific instructions for OpenAI GPT-4o-mini.
- Review feedback aggregated and posted using GitHub Review API.
- Observability via structured logging, tracing IDs, and metrics collection hooks.

## Component Responsibilities
- **FastAPI Application**: expose webhook and internal APIs, manage dependency injection, and orchestrate background tasks.
- **GitHub Integration Layer**: handle app authentication, rate limiting, diff retrieval, and comment posting.
- **Storage Layer (PostgreSQL + SQLModel)**: persist PR state, file snapshots, chunk metadata, review results, and worker job status.
- **Task Queue (Celery)**: coordinate ingestion → analysis → feedback stages, enforce retries/backoff, and parallelize file analysis.
- **Chunking Service**: tree-sitter-based AST traversal for Python + TypeScript; fallback to semantic windowing for other languages; deduplicate overlapping hunks.
- **Prompt Builder**: generate minimal context prompts that highlight diff hunks, surrounding code, commit intent, and risk heuristics.
- **LLM Client**: encapsulate OpenAI calls, response validation, safety filtering, and caching.
- **Review Aggregator**: map LLM findings to GitHub comment positions, group by file, and manage review submission lifecycle.

## Milestones & Tasks
1. **Foundations (Week 1)** (done)
   - Scaffold FastAPI project structure (`app/`, `tests/`, `docs/`).
   - Implement config management for GitHub App credentials, OpenAI keys, PostgreSQL DSN, and Celery settings.
   - Create PostgreSQL schema for PRs, commits, files, and review jobs (SQLModel migrations).
   - Expose webhook endpoint handling `pull_request` opened/synchronized events; enqueue Celery ingestion task.
2. **Diff Ingestion & Storage (Week 2)**
   - Fetch base/head snapshots and diffs; persist metadata and blob references.
   - Classify files by size/complexity; mark large files for chunked processing.
   - Implement idempotent Celery task pipeline for ingestion and retries.
3. **Analysis Pipeline (Week 3)**
   - Integrate tree-sitter for Python/TypeScript AST chunking; fallback plain diff for others.
   - Build semantic chunk metadata (function/class names, complexity tags).
   - Implement prompt builder templates and unit tests.
   - Call OpenAI GPT-4o-mini per file chunk; collect findings.
4. **Feedback Delivery (Week 4)**
   - Map findings to GitHub review comments; handle inline vs summary.
   - Add Celery chain for feedback publishing with error handling & rate limit respect.
   - Instrument logging, metrics, and tracing hooks across services.
   - Document deployment runbooks (Celery worker, Flower, PostgreSQL migrations).

## Success Metrics
- Latency P95 ≤5 minutes across webhook receipt to review post.
- Comment precision ≥0.8 on curated evaluation set.
- Celery task retry success ≥95% after a single retry.
- Monitoring coverage of ingestion, analysis, and feedback spans at 100%.

## Open Questions
- Broker selection for Celery (Redis vs SQS) and corresponding infrastructure readiness.
- Strategy for evaluating large binary or generated files (skip vs heuristic detection).
- Long-term storage of code snapshots (object storage vs inline DB).

