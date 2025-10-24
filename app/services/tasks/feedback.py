from __future__ import annotations

import logging

from app.services.feedback.review_publisher import ReviewPublisher
from app.services.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.services.tasks.feedback.publish_review",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def publish_review(self, analysis_run_id: int) -> dict:
    logger.info("Publishing review", extra={"analysis_run_id": analysis_run_id})
    publisher = ReviewPublisher()
    result = publisher.publish(analysis_run_id)
    logger.info("Review publication completed", extra={"analysis_run_id": analysis_run_id, **result})
    return result
