"""Startup warm-up for the embedding model, off the request path."""

import logging
from threading import Thread

from app.service import deps

logger = logging.getLogger(__name__)


def _load() -> None:
    try:
        embedder = deps.embedder()
        logger.info(
            "Embedding model ready: %s (%d dims)", embedder.model_name, embedder.vector_size()
        )
    except Exception as e:  # a failed warm-up only means the first ingest pays
        logger.warning("Embedding model warm-up failed: %s", e)


def warm_embedder() -> None:
    Thread(target=_load, name="embedder-warmup", daemon=True).start()
