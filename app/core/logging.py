import logging
from logging import Logger

from .config import get_settings


def configure_logging() -> Logger:
    """
    Configure root logger with level from settings.
    """
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    return logging.getLogger("pearl")
