"""Dense multilingual embeddings (BAAI/bge-m3 by default).

One model instance per process, loaded lazily on first use and shared by the
processing worker and query handling. Vectors are L2-normalised so cosine
similarity equals the dot product, matching the pgvector cosine index.
"""

import logging
import threading
import time
from collections.abc import Callable, Sequence

import numpy as np

from app.core.config import Settings, get_settings
from app.models.chunk import EMBEDDING_DIMENSION
from app.rag.errors import ModelUnavailableError
from app.rag.model_store import describe_load_error, resolve_model_path, select_device
from app.rag.tokens import HFTokenCounter

logger = logging.getLogger("lexirag.embeddings")


class EmbeddingModel:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.model_id = settings.embedding_model
        self._model = None
        self._tokenizer_counter: HFTokenCounter | None = None
        self._load_lock = threading.Lock()
        # Forward passes are serialised; batches are small so queries are not starved.
        self._encode_lock = threading.Lock()
        self.device: str | None = None
        self.dimension: int | None = None
        self.load_seconds: float | None = None

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def _load(self):  # noqa: ANN202
        if self._model is not None:
            return self._model
        with self._load_lock:
            if self._model is not None:
                return self._model
            path = resolve_model_path(self.model_id, self.settings)
            device = select_device(self.settings.model_device)
            started = time.perf_counter()
            try:
                from sentence_transformers import SentenceTransformer

                model = SentenceTransformer(str(path), device=device, local_files_only=True)
                model.max_seq_length = self.settings.embedding_max_tokens
            except Exception as exc:  # noqa: BLE001
                raise describe_load_error(self.model_id, exc) from exc
            dimension = model.get_sentence_embedding_dimension()
            expected = self.settings.embedding_dimension
            if dimension != expected or dimension != EMBEDDING_DIMENSION:
                raise ModelUnavailableError(
                    f"{self.model_id} produces {dimension}-dimensional vectors, but the database column "
                    f"stores {EMBEDDING_DIMENSION} (EMBEDDING_DIMENSION={expected}). A new migration and "
                    "re-processing are required to change embedding dimensions."
                )
            self.device = device
            self.dimension = dimension
            self.load_seconds = time.perf_counter() - started
            self._model = model
            self._tokenizer_counter = HFTokenCounter(model.tokenizer)
            logger.info("Loaded %s on %s (dim=%d) in %.1fs", self.model_id, device, dimension, self.load_seconds)
            return model

    def token_counter(self) -> HFTokenCounter:
        self._load()
        assert self._tokenizer_counter is not None
        return self._tokenizer_counter

    def _encode(self, texts: Sequence[str], batch_size: int) -> np.ndarray:
        model = self._load()
        try:
            with self._encode_lock:
                vectors = model.encode(
                    list(texts),
                    batch_size=batch_size,
                    normalize_embeddings=True,
                    convert_to_numpy=True,
                    show_progress_bar=False,
                )
        except Exception as exc:  # noqa: BLE001
            raise describe_load_error(self.model_id, exc) from exc
        vectors = np.asarray(vectors, dtype=np.float32)
        if vectors.ndim != 2 or vectors.shape[1] != self.dimension:
            raise ModelUnavailableError(f"Unexpected embedding shape {vectors.shape} from {self.model_id}.")
        if not np.isfinite(vectors).all():
            raise ModelUnavailableError("The embedding model produced invalid (NaN/inf) values.")
        return vectors

    def embed_documents(
        self, texts: Sequence[str], *, progress: Callable[[int, int], None] | None = None
    ) -> np.ndarray:
        batch = max(1, self.settings.embedding_batch_size)
        parts: list[np.ndarray] = []
        for start in range(0, len(texts), batch):
            # One encode call per batch so the lock is released between batches.
            parts.append(self._encode(texts[start : start + batch], batch))
            if progress:
                progress(min(start + batch, len(texts)), len(texts))
        if not parts:
            return np.zeros((0, self.dimension or EMBEDDING_DIMENSION), dtype=np.float32)
        return np.vstack(parts)

    def embed_query(self, text: str) -> np.ndarray:
        # BGE-M3 needs no query instruction prefix for retrieval.
        return self._encode([text], 1)[0]


_instance: EmbeddingModel | None = None
_instance_lock = threading.Lock()


def get_embedding_model() -> EmbeddingModel:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = EmbeddingModel(get_settings())
    return _instance


def set_embedding_model(model: EmbeddingModel | None) -> None:
    """Testing hook: replace the process-wide model."""
    global _instance
    _instance = model
