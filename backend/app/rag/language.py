"""Language identification for documents, pages, chunks and queries.

Two signals are combined:

1. Unicode script analysis. Gurmukhi text is Punjabi and Bengali-script text is
   Bengali (among LexiRAG's languages), so these need no statistical model.
2. Lingua (an offline n-gram detector) restricted to the six supported languages.
   It separates Hindi from Marathi (both Devanagari) and English from French.

Detection is a hint, not ground truth: short or mixed texts are reported as
"uncertain" or "mixed", and text in other scripts as "unsupported".
"""

import logging
import threading
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

logger = logging.getLogger("lexirag.language")

SUPPORTED = ("en", "hi", "bn", "mr", "pa", "fr")

# Script name -> candidate LexiRAG languages written in it.
SCRIPT_LANGUAGES: dict[str, tuple[str, ...]] = {
    "Latin": ("en", "fr"),
    "Devanagari": ("hi", "mr"),
    "Bengali": ("bn",),
    "Gurmukhi": ("pa",),
}

_RANGES: list[tuple[int, int, str]] = [
    (0x0041, 0x024F, "Latin"),
    (0x1E00, 0x1EFF, "Latin"),
    (0x0900, 0x097F, "Devanagari"),
    (0xA8E0, 0xA8FF, "Devanagari"),
    (0x0980, 0x09FF, "Bengali"),
    (0x0A00, 0x0A7F, "Gurmukhi"),
    (0x0A80, 0x0AFF, "Gujarati"),
    (0x0B00, 0x0B7F, "Odia"),
    (0x0B80, 0x0BFF, "Tamil"),
    (0x0C00, 0x0C7F, "Telugu"),
    (0x0C80, 0x0CFF, "Kannada"),
    (0x0D00, 0x0D7F, "Malayalam"),
    (0x0600, 0x06FF, "Arabic"),
    (0x0400, 0x04FF, "Cyrillic"),
    (0x4E00, 0x9FFF, "Han"),
]

MIN_CHARS_FOR_CONFIDENT = 20
MIXED_SHARE = 0.2


def script_of(char: str) -> str | None:
    code = ord(char)
    for start, end, name in _RANGES:
        if start <= code <= end:
            # Only letters and marks count; digits and punctuation are script-neutral.
            category = unicodedata.category(char)
            if category[0] in ("L", "M"):
                return name
            return None
    return None


def script_counts(text: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    for char in text:
        script = script_of(char)
        if script:
            counts[script] += 1
    return counts


@dataclass
class LanguageResult:
    language: str | None  # supported code, or None when uncertain/unsupported
    confidence: float  # 0..1, share-weighted; not a calibrated probability
    status: str  # detected | mixed | uncertain | unsupported | empty
    distribution: dict[str, float] = field(default_factory=dict)
    scripts: dict[str, int] = field(default_factory=dict)

    def as_details(self) -> dict[str, object]:
        return {
            "status": self.status,
            "confidence": round(self.confidence, 3),
            "distribution": {k: round(v, 3) for k, v in self.distribution.items()},
            "scripts": self.scripts,
        }


class _LinguaHolder:
    """Builds the Lingua detector once; it is thread-safe for detection."""

    _lock = threading.Lock()
    _detector = None
    _failed = False

    @classmethod
    def get(cls):  # noqa: ANN206
        if cls._detector is not None or cls._failed:
            return cls._detector
        with cls._lock:
            if cls._detector is None and not cls._failed:
                try:
                    from lingua import Language, LanguageDetectorBuilder

                    cls._detector = (
                        LanguageDetectorBuilder.from_languages(
                            Language.ENGLISH,
                            Language.FRENCH,
                            Language.HINDI,
                            Language.MARATHI,
                            Language.BENGALI,
                            Language.PUNJABI,
                        )
                        .with_preloaded_language_models()
                        .build()
                    )
                except Exception:  # noqa: BLE001
                    logger.exception("Lingua could not be initialised; using script analysis only")
                    cls._failed = True
        return cls._detector


_LINGUA_CODES = {"ENGLISH": "en", "FRENCH": "fr", "HINDI": "hi", "MARATHI": "mr", "BENGALI": "bn", "PUNJABI": "pa"}


def _disambiguate(text: str, candidates: tuple[str, ...]) -> tuple[str, float]:
    """Pick between languages sharing a script (hi/mr, en/fr). Returns (code, confidence)."""
    if len(candidates) == 1:
        return candidates[0], 1.0
    detector = _LinguaHolder.get()
    if detector is None:
        return candidates[0], 0.5
    sample = text[:4000]
    scores: dict[str, float] = {}
    for value in detector.compute_language_confidence_values(sample):
        code = _LINGUA_CODES.get(value.language.name)
        if code in candidates:
            scores[code] = value.value
    if not scores:
        return candidates[0], 0.5
    total = sum(scores.values()) or 1.0
    best = max(scores, key=scores.get)
    return best, scores[best] / total


def detect_language(text: str) -> LanguageResult:
    counts = script_counts(text)
    letters = sum(counts.values())
    if letters == 0:
        return LanguageResult(None, 0.0, "empty")

    supported_letters = sum(n for s, n in counts.items() if s in SCRIPT_LANGUAGES)
    if supported_letters / letters < 0.5:
        return LanguageResult(None, 0.0, "unsupported", scripts=dict(counts))

    distribution: dict[str, float] = {}
    for script, n in counts.items():
        candidates = SCRIPT_LANGUAGES.get(script)
        if not candidates:
            continue
        share = n / letters
        if share < 0.05:
            continue
        # Restrict the disambiguation sample to that script's characters plus spaces.
        sample = "".join(ch if (script_of(ch) == script or ch.isspace()) else " " for ch in text)
        code, conf = _disambiguate(sample, candidates)
        distribution[code] = distribution.get(code, 0.0) + share * conf
        # Keep residual mass on the alternative so "mixed" reflects real uncertainty.
        for other in candidates:
            if other != code:
                distribution[other] = distribution.get(other, 0.0) + share * (1 - conf)

    if not distribution:
        return LanguageResult(None, 0.0, "uncertain", scripts=dict(counts))

    primary = max(distribution, key=distribution.get)
    confidence = distribution[primary]
    secondary = sorted((v for k, v in distribution.items() if k != primary), reverse=True)
    if letters < MIN_CHARS_FOR_CONFIDENT or confidence < 0.5:
        status = "uncertain"
    elif secondary and secondary[0] >= MIXED_SHARE and _scripts_differ(counts):
        status = "mixed"
    else:
        status = "detected"
    language = primary if status in ("detected", "mixed") or confidence >= 0.4 else None
    return LanguageResult(
        language=language,
        confidence=confidence,
        status=status,
        distribution={k: v for k, v in sorted(distribution.items(), key=lambda kv: -kv[1]) if v >= 0.01},
        scripts=dict(counts),
    )


def _scripts_differ(counts: Counter[str]) -> bool:
    letters = sum(counts.values())
    significant = [s for s, n in counts.items() if n / letters >= MIXED_SHARE]
    return len(significant) > 1


def detect_document_language(page_texts: list[str]) -> LanguageResult:
    """Aggregate per-page detection, weighting pages by their amount of text."""
    weights: Counter[str] = Counter()
    scripts: Counter[str] = Counter()
    total = 0
    for text in page_texts:
        if not text.strip():
            continue
        result = detect_language(text)
        n = sum(result.scripts.values())
        scripts.update(result.scripts)
        if result.language is None:
            total += n
            continue
        for code, share in result.distribution.items():
            weights[code] += share * n
        total += n
    if total == 0:
        return LanguageResult(None, 0.0, "empty")
    if not weights:
        return LanguageResult(None, 0.0, "unsupported", scripts=dict(scripts))
    distribution = {code: w / total for code, w in weights.most_common()}
    primary, confidence = next(iter(distribution.items()))
    secondary = [v for k, v in distribution.items() if k != primary]
    if confidence < 0.5:
        status = "uncertain" if not secondary or secondary[0] < MIXED_SHARE else "mixed"
    elif secondary and secondary[0] >= MIXED_SHARE:
        status = "mixed"
    else:
        status = "detected"
    return LanguageResult(
        language=primary if confidence >= 0.3 else None,
        confidence=confidence,
        status=status,
        distribution={k: v for k, v in distribution.items() if v >= 0.01},
        scripts=dict(scripts),
    )
