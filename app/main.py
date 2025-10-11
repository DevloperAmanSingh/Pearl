import logging

from fastapi import FastAPI

from app.api.routes_review import router as review_router
from app.core.config import get_settings
from app.core.logging import configure_logging


configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="Pearl AI Code Review", version="0.1.0")
app.include_router(review_router)


@app.on_event("startup")
async def startup_event() -> None:
    settings = get_settings()
    logger.info("Starting application", extra={"environment": settings.environment})
