import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request, status

from app.core.config import get_settings
from app.services.tasks.ingestion import enqueue_pull_request_ingestion


router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = logging.getLogger(__name__)


@router.post(
    "/github",
    status_code=status.HTTP_202_ACCEPTED,
    summary="GitHub webhook receiver",
)
async def handle_github_webhook(request: Request) -> Dict[str, Any]:
    event = request.headers.get("X-GitHub-Event")
    if event is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing X-GitHub-Event header")

    payload = await request.json()
    delivery_id = request.headers.get("X-GitHub-Delivery")
    if delivery_id:
        payload["delivery_id"] = delivery_id

    if event != "pull_request":
        logger.debug("Ignoring unsupported GitHub event", extra={"event": event})
        return {"status": "ignored", "reason": "unsupported_event"}

    settings = get_settings()
    action = payload.get("action")

    if action not in settings.github_event_actions:
        logger.debug("Ignoring pull request action", extra={"action": action})
        return {"status": "ignored", "reason": f"action_{action}"}

    enqueue_pull_request_ingestion(payload)
    pr_number = payload.get("pull_request", {}).get("number")
    repo = payload.get("repository", {}).get("full_name")
    logger.info("Enqueued pull request ingestion", extra={"repository": repo, "pr_number": pr_number})
    return {"status": "queued", "repository": repo, "pr_number": pr_number}
