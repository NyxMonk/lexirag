"""Token counting for chunk sizing.

Chunk budgets are expressed in the embedding model's own tokens (BGE-M3 uses
the XLM-RoBERTa SentencePiece vocabulary), so a "700-token" chunk means the same
thing for English, Hindi or Gurmukhi text. A heuristic counter exists for tests
and for environments where the tokenizer is not downloaded.
"""

import logging
import re
import threading
from typing import Protocol

logger = logging.getLogger("lexirag.tokens")


class TokenCounter(Protocol):
    name: str

    def count(self, text: str) -> int: ...


class HeuristicTokenCounter:
    """Approximates SentencePiece counts: ~1 token per short word, more for long words.

    Indic words are split into more pieces than English ones by XLM-R, so words
    are weighted by length. Accurate to roughly ±25%, which is fine for tests.
    """

    name = "heuristic"
    _word = re.compile(r"\S+")

    def count(self, text: str) -> int:
        total = 0
        for match in self._word.finditer(text):
            n = len(match.group())
            total += 1 if n <= 4 else 1 + n // 5
        return total


class HFTokenCounter:
    def __init__(self, tokenizer) -> None:  # noqa: ANN001
        self._tokenizer = tokenizer
        self._lock = threading.Lock()
        self.name = getattr(tokenizer, "name_or_path", "hf")

    def count(self, text: str) -> int:
        if not text:
            return 0
        with self._lock:
            return len(self._tokenizer(text, add_special_tokens=False, truncation=False)["input_ids"])
