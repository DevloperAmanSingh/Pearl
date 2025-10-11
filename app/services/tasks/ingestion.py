import logging
from typing import Any, Dict

from app.services.ingestion.pr_processor import process_pull_request
from app.services.tasks.celery_app import celery_app


logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.services.tasks.ingestion.ingest_pull_request",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 5},
)
def ingest_pull_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    pull_request = payload.get("pull_request", {})
    repository = payload.get("repository", {})

    pr_number = pull_request.get("number")
    repo_full_name = repository.get("full_name")

    logger.info(
        "Starting ingestion for pull request",
        extra={"repository": repo_full_name, "pr_number": pr_number, "delivery": payload.get("delivery_id")},
    )

    result = process_pull_request(payload)
    logger.info(
        "Completed ingestion for pull request",
        extra={"repository": repo_full_name, "pr_number": pr_number, "commits": result["commit_count"], "files": result["file_count"]},
    )
    return {"status": "completed", **result}


def enqueue_pull_request_ingestion(payload: Dict[str, Any]) -> None:
    """
    Submit the payload to Celery for asynchronous processing.
    """
    ingest_pull_request.delay(payload)
