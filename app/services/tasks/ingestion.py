import logging
from typing import Any, Dict

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
    """
    Placeholder ingestion task that will later orchestrate diff collection.
    """
    pull_request = payload.get("pull_request", {})
    repository = payload.get("repository", {})

    pr_number = pull_request.get("number")
    repo_full_name = repository.get("full_name")

    logger.info(
        "Ingestion task received pull request",
        extra={"repository": repo_full_name, "pr_number": pr_number, "delivery": payload.get("delivery_id")},
    )

    return {"status": "received", "repository": repo_full_name, "pr_number": pr_number}


def enqueue_pull_request_ingestion(payload: Dict[str, Any]) -> None:
    """
    Submit the payload to Celery for asynchronous processing.
    """
    ingest_pull_request.delay(payload)
