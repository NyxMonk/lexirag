"""Background model warm-up at startup.

Loading BGE-M3 and the reranker (and initialising CUDA) takes tens of seconds, which otherwise
lands on the first question. This loads them from the local cache in a daemon thread, so the API
starts immediately. It never downloads: a missing model is logged and left to the usual
actionable error on first use.
"""

import logging
import threading
import time

from app.core.config import get_settings

logger = logging.getLogger("lexirag.warmup")


def _warm() -> None:
    from app.rag.embeddings import get_embedding_model
    from app.rag.reranking import get_reranker

    started = time.perf_counter()
    try:
        get_embedding_model().embed_query("warm-up")
        reranker = get_reranker()
        if reranker is not None:
            reranker.score("warm-up", ["warm-up"])
    except Exception as exc:  # noqa: BLE001 - warm-up is best effort
        logger.warning("Model warm-up skipped: %s", exc)
        return
    logger.info("Models warmed up in %.1fs", time.perf_counter() - started)


def start_warmup() -> threading.Thread | None:
    if not get_settings().models_warmup:
        return None
    thread = threading.Thread(target=_warm, name="model-warmup", daemon=True)
    thread.start()
    return thread
