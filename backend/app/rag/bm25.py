"""BM25 keyword retrieval with a tokenizer suited to legal text in Indian scripts.

Design choices:

* Tokens are maximal runs of letters, combining marks and digits, so Devanagari,
  Bengali and Gurmukhi vowel signs (which are combining marks, not letters) stay
  inside their words.
* No stemming and no stopword removal: English-only rules would damage Indic
  text, and BM25's IDF already discounts very common words.
* Legal references are kept as extra tokens: "12(3)(a)", "138", "S.138",
  "Article 21" -> "article_21". Indic digits are mapped to ASCII so "धारा १२"
  matches "Section 12".
"""

import re
import unicodedata
from collections.abc import Sequence

from rank_bm25 import BM25Okapi

# Devanagari, Bengali, Gurmukhi and other Indic digits -> ASCII.
_DIGIT_MAP = {}
for _base in (0x0966, 0x09E6, 0x0A66, 0x0AE6, 0x0B66, 0x0BE6, 0x0C66, 0x0CE6, 0x0D66):
    for _i in range(10):
        _DIGIT_MAP[_base + _i] = ord("0") + _i

_LEGAL_REF = re.compile(r"\b\d+[A-Za-z]?(?:\(\s*[0-9A-Za-z]{1,4}\s*\))+")
_PREFIXED_REF = re.compile(
    r"\b(section|sec|s|article|art|clause|cl|rule|order|schedule|chapter|para)\.?\s*(\d+[A-Za-z]?)",
    re.IGNORECASE,
)


def _is_word_char(char: str) -> bool:
    category = unicodedata.category(char)
    return category[0] in ("L", "M", "N") or char == "_"


def normalise(text: str) -> str:
    return unicodedata.normalize("NFC", text).translate(_DIGIT_MAP).casefold()


def tokenize(text: str) -> list[str]:
    text = normalise(text)
    tokens: list[str] = []
    current: list[str] = []
    for char in text:
        if _is_word_char(char):
            current.append(char)
        elif current:
            tokens.append("".join(current))
            current = []
    if current:
        tokens.append("".join(current))

    # Composite legal references as additional tokens.
    for match in _LEGAL_REF.finditer(text):
        tokens.append(re.sub(r"\s+", "", match.group()))
    for match in _PREFIXED_REF.finditer(text):
        prefix = match.group(1).lower()
        prefix = {"sec": "section", "s": "section", "art": "article", "cl": "clause"}.get(prefix, prefix)
        tokens.append(f"{prefix}_{match.group(2).lower()}")
    return tokens


class BM25Index:
    """BM25 over a fixed list of documents (chunk texts), identified by keys."""

    def __init__(self, keys: Sequence[object], texts: Sequence[str]) -> None:
        if len(keys) != len(texts):
            raise ValueError("keys and texts must have the same length")
        self.keys = list(keys)
        self._tokenized = [tokenize(t) for t in texts]
        # rank_bm25 divides by the corpus size; guard the empty corpus.
        self._bm25 = BM25Okapi(self._tokenized) if self.keys else None

    def __len__(self) -> int:
        return len(self.keys)

    def search(
        self, query: str, top_k: int, *, allowed: set[object] | None = None
    ) -> list[tuple[object, float]]:
        if self._bm25 is None:
            return []
        query_tokens = tokenize(query)
        if not query_tokens:
            return []
        scores = self._bm25.get_scores(query_tokens)
        ranked = sorted(range(len(self.keys)), key=lambda i: scores[i], reverse=True)
        results: list[tuple[object, float]] = []
        for i in ranked:
            if scores[i] <= 0:
                break  # no query term occurs in this or any lower-ranked chunk
            key = self.keys[i]
            if allowed is not None and key not in allowed:
                continue
            results.append((key, float(scores[i])))
            if len(results) >= top_k:
                break
        return results
