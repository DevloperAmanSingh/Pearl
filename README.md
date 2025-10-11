# Pearl AI Code Review

Phase 1 focuses on building the ingestion and task orchestration layer for an AI-assisted pull request reviewer powered by FastAPI, Celery, and PostgreSQL.

## Getting Started

1. Install dependencies with [uv](https://github.com/astral-sh/uv):
   ```bash
   uv sync
   ```
2. Copy `.env.example` to `.env` and fill GitHub, OpenAI, PostgreSQL, and Redis settings.
3. Run database migrations (coming in later phases). For now, create tables with:
   ```bash
   uv run python -c "from app.db.session import init_db; init_db()"
   ```
4. Start the API:
   ```bash
   uv run uvicorn app.main:app --reload
   ```
5. Start Celery worker:
   ```bash
   uv run celery -A app.services.tasks.celery_app.celery_app worker --loglevel=info
   ```

## Documentation

- Phase plan: `docs/phase1_prd.md`
