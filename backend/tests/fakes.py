"""Deterministic stand-ins for model-backed components (used only in tests).

The fake embedder hashes word tokens into a 1024-dimensional bag-of-words vector.
It has lexical (not semantic, not cross-lingual) similarity, which is enough to
test the pipeline, storage and API wiring without downloading BGE-M3.
"""

import hashlib
import json
from collections.abc import Callable, Sequence

import numpy as np

from app.models.chunk import EMBEDDING_DIMENSION
from app.rag.bm25 import tokenize
from app.rag.llm import Generation
from app.rag.tokens import HeuristicTokenCounter


class FakeEmbeddingModel:
    model_id = "fake-hash-embedder"
    device = "cpu"
    dimension = EMBEDDING_DIMENSION
    loaded = True
    load_seconds = 0.0

    def __init__(self) -> None:
        self.calls = 0

    def token_counter(self) -> HeuristicTokenCounter:
        return HeuristicTokenCounter()

    def _vector(self, text: str) -> np.ndarray:
        vec = np.zeros(EMBEDDING_DIMENSION, dtype=np.float32)
        for token in tokenize(text):
            h = int(hashlib.md5(token.encode()).hexdigest(), 16)
            vec[h % EMBEDDING_DIMENSION] += 1.0
        norm = np.linalg.norm(vec)
        if norm == 0:
            vec[0] = 1.0
            norm = 1.0
        return vec / norm

    def embed_documents(self, texts: Sequence[str], *, progress: Callable[[int, int], None] | None = None) -> np.ndarray:
        self.calls += 1
        vectors = np.vstack([self._vector(t) for t in texts]) if texts else np.zeros((0, EMBEDDING_DIMENSION))
        if progress:
            progress(len(texts), len(texts))
        return vectors

    def embed_query(self, text: str) -> np.ndarray:
        return self._vector(text)


class FakeLLM:
    """Returns a scripted response. By default it cites S1 with a verbatim quote from the prompt."""

    name = "fake"
    model = "fake-llm"

    def __init__(self) -> None:
        self.prompts: list[tuple[str, str]] = []
        self.responses: list[str] = []

    def queue(self, payload: dict | str) -> None:
        self.responses.append(payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False))

    def generate(self, system: str, user: str) -> Generation:
        self.prompts.append((system, user))
        if self.responses:
            text = self.responses.pop(0)
        else:
            source = user.split('<source id="S1"', 1)[1].split(">", 1)[1].split("</source>", 1)[0].strip()
            quote = source.split("\n\n")[-1][:80]
            text = json.dumps(
                {
                    "answer": "Synthetic answer based on the first source [S1].",
                    "evidence_sufficient": True,
                    "citations": [{"source_id": "S1", "quote": quote}],
                },
                ensure_ascii=False,
            )
        return Generation(text=text, provider=self.name, model=self.model, duration_ms=1.0, stop_reason="stop")
