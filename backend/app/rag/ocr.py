"""Optional Tesseract OCR for scanned pages.

OCR is an enhancement: if Tesseract (or a language pack) is missing, pages that
need OCR are reported as skipped, and documents with other extractable text are
still processed.
"""

import logging
import shutil
from dataclasses import dataclass, field
from functools import lru_cache

from app.rag.errors import OcrUnavailableError

logger = logging.getLogger("lexirag.ocr")

# Tesseract language packs for LexiRAG's languages.
TESSERACT_LANGS = {"en": "eng", "hi": "hin", "bn": "ben", "mr": "mar", "pa": "pan", "fr": "fra"}


@dataclass(frozen=True)
class OcrStatus:
    available: bool
    version: str | None = None
    installed_languages: tuple[str, ...] = ()
    requested_languages: tuple[str, ...] = ()
    missing_languages: tuple[str, ...] = ()
    message: str | None = None
    usable_languages: tuple[str, ...] = field(default=())


def _configure(tesseract_cmd: str) -> object | None:
    try:
        import pytesseract
    except ImportError:  # pragma: no cover - dependency is pinned
        return None
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
    return pytesseract


@lru_cache(maxsize=4)
def ocr_status(tesseract_cmd: str, requested: str) -> OcrStatus:
    requested_langs = tuple(lang for lang in requested.split("+") if lang)
    pytesseract = _configure(tesseract_cmd)
    if pytesseract is None:
        return OcrStatus(False, message="pytesseract is not installed.", requested_languages=requested_langs)
    if not tesseract_cmd and shutil.which("tesseract") is None:
        return OcrStatus(
            False,
            requested_languages=requested_langs,
            message="Tesseract OCR is not installed or not on PATH (set TESSERACT_CMD). "
            "Scanned pages cannot be read.",
        )
    try:
        version = str(pytesseract.get_tesseract_version())
        installed = tuple(sorted(pytesseract.get_languages(config="")))
    except Exception as exc:  # noqa: BLE001
        return OcrStatus(
            False,
            requested_languages=requested_langs,
            message=f"Tesseract could not be started ({exc.__class__.__name__}). Check TESSERACT_CMD.",
        )
    missing = tuple(lang for lang in requested_langs if lang not in installed)
    usable = tuple(lang for lang in requested_langs if lang in installed)
    message = None
    if missing:
        message = (
            "Missing Tesseract language packs: " + ", ".join(missing) + ". "
            "Install them to OCR scanned pages in those languages."
        )
    return OcrStatus(
        available=bool(usable),
        version=version,
        installed_languages=installed,
        requested_languages=requested_langs,
        missing_languages=missing,
        usable_languages=usable,
        message=message if usable else (message or "No requested OCR language packs are installed."),
    )


def ocr_image(image: object, *, tesseract_cmd: str, languages: str) -> str:
    """OCR a PIL image with every usable requested language pack."""
    status = ocr_status(tesseract_cmd, languages)
    if not status.available:
        raise OcrUnavailableError(status.message or "OCR is unavailable.")
    pytesseract = _configure(tesseract_cmd)
    # --psm 3: fully automatic page segmentation; keeps paragraph breaks as blank lines.
    return pytesseract.image_to_string(image, lang="+".join(status.usable_languages), config="--psm 3")
