"""Cross-encoder reranking (BAAI/bge-reranker-v2-m3 by default).

The reranker scores (query, passage) pairs jointly, which works across
languages (Hindi question, English passage). It is optional: when disabled or
unavailable, the fused retrieval order is used and the response says so.
"""

import logging
import threading
import time
from collections.abc import Sequence
from typing import Protocol

from app.core.config import Settings, get_settings
from app.rag.model_store import describe_load_error, resolve_model_path, select_device

logger = logging.getLogger("lexirag.reranking")


class Reranker(Protocol):
    model_id: str

    def score(self, query: str, passages: Sequence[str]) -> list[float]: ...


class CrossEncoderReranker:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.model_id = settings.reranker_model
        self._model = None
        self._load_lock = threading.Lock()
        self._predict_lock = threading.Lock()
        self.device: str | None = None
        self.load_seconds: float | None = None

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def _load(self):  # noqa: ANN202
        if self._model is not None:
            return self._model
        with self._load_lock:
            if self._model is None:
                path = resolve_model_path(self.model_id, self.settings)
                device = select_device(self.settings.model_device)
                started = time.perf_counter()
                try:
                    from sentence_transformers import CrossEncoder

                    model = CrossEncoder(
                        str(path),
                        device=device,
                        max_length=self.settings.reranker_max_tokens,
                        local_files_only=True,
                    )
                except Exception as exc:  # noqa: BLE001
                    raise describe_load_error(self.model_id, exc) from exc
                self.device = device
                self.load_seconds = time.perf_counter() - started
                self._model = model
                logger.info("Loaded reranker %s on %s in %.1fs", self.model_id, device, self.load_seconds)
        return self._model

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        if not passages:
            return []
        model = self._load()
        try:
            with self._predict_lock:
                scores = model.predict(
                    [(query, p) for p in passages],
                    batch_size=self.settings.reranker_batch_size,
                    show_progress_bar=False,
                    convert_to_numpy=True,
                )
        except Exception as exc:  # noqa: BLE001
            raise describe_load_error(self.model_id, exc) from exc
        return [float(s) for s in scores]


_instance: Reranker | None = None
_instance_lock = threading.Lock()


def get_reranker() -> Reranker | None:
    """The configured reranker, or None when reranking is disabled."""
    global _instance
    settings = get_settings()
    if not settings.reranker_enabled:
        return None
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = CrossEncoderReranker(settings)
    return _instance


def set_reranker(reranker: Reranker | None) -> None:
    """Testing hook."""
    global _instance
    _instance = reranker
