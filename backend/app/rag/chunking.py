"""Legal-aware chunking.

Chunks are built from paragraph blocks (never from one merged string), so each
chunk keeps the pages it came from. The algorithm:

1. Walk paragraphs in reading order. Paragraphs that look like headings
   (Section/Clause/Article/Chapter/धारा/ধারা/ਧਾਰਾ/numbered titles/ALL CAPS)
   start a new section and become the ``section_title`` of following chunks.
2. Accumulate paragraphs until the target size would be exceeded. A new section
   closes the current chunk if it already has ``min_tokens``.
3. Paragraphs larger than the target are split at sentence boundaries
   (., ?, !, ।, ॥, ;); sentences larger than the target are split by words.
4. Consecutive chunks inside a section overlap by whole trailing sentences up
   to ``overlap_tokens``. No overlap is carried across section boundaries.
"""

import re
from dataclasses import dataclass

from app.rag.extraction import PageText
from app.rag.language import SCRIPT_LANGUAGES, detect_language
from app.rag.tokens import TokenCounter

# Headings commonly found in Indian statutes, contracts and judgments, in the supported languages.
_HEADING_KEYWORDS = (
    r"(?:section|sec\.|clause|article|chapter|part|schedule|annexure|appendix|rule|order|recital|"
    r"definitions?|preamble|whereas|"
    r"धारा|अनुच्छेद|अध्याय|खंड|खण्ड|भाग|अनुसूची|नियम|कलम|प्रकरण|परिशिष्ट|"
    r"ধারা|অনুচ্ছেদ|অধ্যায়|অধ্যায়|অংশ|তফসিল|"
    r"ਧਾਰਾ|ਅਨੁਛੇਦ|ਅਧਿਆਇ|ਭਾਗ|ਅਨੁਸੂਚੀ|"
    r"chapitre|titre|annexe|partie)"
)
# Explicit lookahead instead of \b: Indic vowel signs are not \w, so \b fails after "धारा".
_HEADING_KEYWORD_RE = re.compile(rf"^\s*{_HEADING_KEYWORDS}(?=[\s\d\.\-–—:()]|$)", re.IGNORECASE)
_NUMBERED_TITLE_RE = re.compile(r"^\s*(?:\d+|[IVXLC]+|[०-९]+|[০-৯]+|[੦-੯]+)(?:\.\d+)*[\.\)]?\s+\S")
# Sentence ends: Latin punctuation, Devanagari/Bengali/Gurmukhi danda and double danda, semicolon.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[\.\?\!।॥;])\s+")
# Abbreviations that must not end a sentence ("Sec. 12", "No. 4", "v. State").
_NO_BREAK_BEFORE_RE = re.compile(r"(?:\b(?:sec|no|art|cl|vs?|viz|i\.e|e\.g|etc|mr|mrs|dr|rs|s|ss|para|pp?)\.)$", re.IGNORECASE)

MAX_HEADING_CHARS = 120
SAME_SCRIPT_OVERRIDE_CONFIDENCE = 0.85


@dataclass(frozen=True)
class Chunk:
    index: int
    content: str
    page_start: int
    page_end: int
    section_title: str | None
    token_count: int
    language: str | None
    # [[page, start, end], ...] character offsets of each page's text within ``content``.
    page_spans: tuple[tuple[int, int, int], ...] = ()
    # [[start, title], ...]: the section in force from ``start`` until the next entry.
    section_spans: tuple[tuple[int, str], ...] = ()

    def page_at(self, offset: int) -> int:
        for page, start, end in self.page_spans:
            if start <= offset < end:
                return page
        return self.page_start

    def section_at(self, offset: int) -> str | None:
        title = self.section_title
        for start, name in self.section_spans:
            if start <= offset:
                title = name
        return title


def page_spans_for(units: list[tuple[str, int]], separator: str = "\n\n") -> tuple[tuple[int, int, int], ...]:
    """Character spans per page for texts joined with ``separator``. Adjacent same-page units merge."""
    spans: list[list[int]] = []
    offset = 0
    for i, (text, page) in enumerate(units):
        start = offset
        end = start + len(text)
        if spans and spans[-1][0] == page:
            spans[-1][2] = end
        else:
            spans.append([page, start, end])
        offset = end + (len(separator) if i < len(units) - 1 else 0)
    return tuple((p, s, e) for p, s, e in spans)


def section_spans_for(units: list[tuple[str, str | None]], separator: str = "\n\n") -> tuple[tuple[int, str], ...]:
    """Start offsets where the section in force changes, for texts joined with ``separator``."""
    spans: list[tuple[int, str]] = []
    offset = 0
    previous: str | None = None
    for text, section in units:
        if section and section != previous:
            spans.append((offset, section))
        previous = section
        offset += len(text) + len(separator)
    return tuple(spans)


@dataclass
class _Unit:
    text: str
    page: int
    tokens: int
    section: str | None = None


def is_heading(paragraph: str) -> bool:
    text = paragraph.strip()
    if not text or len(text) > MAX_HEADING_CHARS:
        return False
    if _HEADING_KEYWORD_RE.match(text):
        # "Section 12. Termination" or "धारा 5" - but not a long sentence that merely starts so.
        return len(text.split()) <= 14 and not text.endswith((",", ";"))
    if _NUMBERED_TITLE_RE.match(text):
        words = text.split()
        return len(words) <= 10 and not text.rstrip().endswith((".", ",", ";", ":", "।"))
    letters = [c for c in text if c.isalpha()]
    if len(letters) >= 4 and all(c.isupper() for c in letters if c.isascii()) and any(c.isascii() for c in letters):
        ascii_letters = [c for c in letters if c.isascii()]
        return len(ascii_letters) / len(letters) > 0.8 and len(text.split()) <= 12
    return False


def split_sentences(text: str) -> list[str]:
    parts = _SENTENCE_SPLIT_RE.split(text)
    sentences: list[str] = []
    for part in parts:
        if sentences and _NO_BREAK_BEFORE_RE.search(sentences[-1]):
            sentences[-1] = f"{sentences[-1]} {part}"
        else:
            sentences.append(part)
    return [s.strip() for s in sentences if s.strip()]


class LegalChunker:
    def __init__(
        self,
        counter: TokenCounter,
        *,
        target_tokens: int = 700,
        overlap_tokens: int = 120,
        min_tokens: int = 120,
    ) -> None:
        if target_tokens <= 0:
            raise ValueError("target_tokens must be positive")
        if not 0 <= overlap_tokens < target_tokens:
            raise ValueError("overlap_tokens must be >= 0 and smaller than target_tokens")
        self.counter = counter
        self.target = target_tokens
        self.overlap = overlap_tokens
        self.min_tokens = min(min_tokens, target_tokens)

    # ── unit preparation ──
    def _split_oversized(self, text: str, page: int) -> list[_Unit]:
        units: list[_Unit] = []
        for sentence in split_sentences(text):
            n = self.counter.count(sentence)
            if n <= self.target:
                units.append(_Unit(sentence, page, n))
                continue
            words = sentence.split()
            current: list[str] = []
            for word in words:
                candidate = " ".join([*current, word])
                if current and self.counter.count(candidate) > self.target:
                    piece = " ".join(current)
                    units.append(_Unit(piece, page, self.counter.count(piece)))
                    current = [word]
                else:
                    current.append(word)
            if current:
                piece = " ".join(current)
                units.append(_Unit(piece, page, self.counter.count(piece)))
        return units

    # ── main ──
    def chunk(self, pages: list[PageText], *, default_language: str | None = None) -> list[Chunk]:
        chunks: list[Chunk] = []
        current: list[_Unit] = []
        current_tokens = 0
        section: str | None = None
        chunk_section: str | None = None

        def flush(carry_overlap: bool) -> None:
            nonlocal current, current_tokens, chunk_section
            if not current:
                return
            content = "\n\n".join(u.text for u in current)
            language = self._chunk_language(content, default_language)
            chunks.append(
                Chunk(
                    index=len(chunks),
                    content=content,
                    page_start=min(u.page for u in current),
                    page_end=max(u.page for u in current),
                    section_title=chunk_section,
                    token_count=self.counter.count(content),
                    language=language,
                    page_spans=page_spans_for([(u.text, u.page) for u in current]),
                    section_spans=section_spans_for([(u.text, u.section) for u in current]),
                )
            )
            tail = self._overlap_tail(current) if carry_overlap else []
            current = tail
            current_tokens = sum(u.tokens for u in tail)
            chunk_section = section

        for page in pages:
            for paragraph in page.blocks:
                paragraph = paragraph.strip()
                if not paragraph:
                    continue
                if is_heading(paragraph):
                    if current_tokens >= self.min_tokens:
                        flush(carry_overlap=False)
                    section = paragraph[:300]
                    if not current:
                        chunk_section = section
                    elif chunk_section is None:
                        chunk_section = section
                    # Headings are kept in the text: they carry clause numbers people search for.
                n = self.counter.count(paragraph)
                units = [_Unit(paragraph, page.number, n)] if n <= self.target else self._split_oversized(paragraph, page.number)
                for unit in units:
                    unit.section = section
                    if current and current_tokens + unit.tokens > self.target:
                        flush(carry_overlap=True)
                    if not current:
                        chunk_section = section
                    current.append(unit)
                    current_tokens += unit.tokens
        flush(carry_overlap=False)
        return chunks

    def _overlap_tail(self, units: list[_Unit]) -> list[_Unit]:
        """Trailing sentences of the closed chunk, up to the overlap budget."""
        if self.overlap == 0:
            return []
        tail: list[_Unit] = []
        budget = self.overlap
        for unit in reversed(units):
            sentences = split_sentences(unit.text)
            for sentence in reversed(sentences):
                n = self.counter.count(sentence)
                if n > budget:
                    if not tail:
                        # No whole sentence fits: carry the trailing words instead.
                        words = sentence.split()
                        kept: list[str] = []
                        while words and self.counter.count(" ".join([words[-1], *kept])) <= budget:
                            kept.insert(0, words.pop())
                        if kept and words:
                            text = " ".join(kept)
                            tail.append(_Unit(text, unit.page, self.counter.count(text), unit.section))
                    return list(reversed(tail))
                tail.append(_Unit(sentence, unit.page, n, unit.section))
                budget -= n
        # Never carry the entire previous chunk forward.
        if sum(u.tokens for u in tail) >= sum(u.tokens for u in units):
            return []
        return list(reversed(tail))

    @staticmethod
    def _chunk_language(content: str, default_language: str | None) -> str | None:
        result = detect_language(content)
        if not result.language or result.status not in ("detected", "mixed"):
            return default_language or result.language
        if default_language and result.language != default_language:
            # Same-script pairs (hi/mr, en/fr) are hard to separate in short chunks; the
            # document-level detection uses far more text, so it wins unless the chunk is clear-cut.
            same_script = any(
                result.language in langs and default_language in langs for langs in SCRIPT_LANGUAGES.values()
            )
            if same_script and result.confidence < SAME_SCRIPT_OVERRIDE_CONFIDENCE:
                return default_language
        return result.language
