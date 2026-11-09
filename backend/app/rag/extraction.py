"""Page-by-page PDF text extraction with PyMuPDF and an OCR fallback.

Text is kept as paragraph blocks per page, so later stages can respect
paragraph boundaries and cite exact pages. Nothing is merged across pages here.
"""

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from app.rag.errors import ExtractionError, OcrUnavailableError
from app.rag.ocr import ocr_image, ocr_status

logger = logging.getLogger("lexirag.extraction")

_SPACES = re.compile(r"[ \t  -​  　]+")
# Latin end-of-line hyphenation: "termin-\nation" -> "termination".
_HYPHEN_BREAK = re.compile(r"(?<=[a-zà-ÿ])-\n(?=[a-zà-ÿ])")
_BLANK_LINES = re.compile(r"\n\s*\n+")
# Text extraction sometimes inserts a space before an Indic dependent vowel sign or
# virama (e.g. Bengali "চাকর ির"). Such a space is never valid, so it is removed.
_SPACE_BEFORE_INDIC_MARK = re.compile(
    r"[ \t]+(?=[ऀ-ःऺ-ॏ॑-ॗॢॣ"
    r"ঁ-ঃ়া-্ৗৢৣ"
    r"ਁ-ਃ਼-ੑੰੱੵ])"
)


@dataclass
class PageText:
    number: int  # 1-based, as shown in PDF viewers
    blocks: list[str]
    method: str  # "text" | "ocr" | "empty" | "ocr_unavailable"

    @property
    def text(self) -> str:
        return "\n\n".join(self.blocks)

    @property
    def char_count(self) -> int:
        return sum(len(b) for b in self.blocks)


@dataclass
class ExtractionResult:
    pages: list[PageText]
    warnings: list[str] = field(default_factory=list)

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def total_chars(self) -> int:
        return sum(p.char_count for p in self.pages)

    def summary(self) -> dict[str, object]:
        def numbers(method: str) -> list[int]:
            return [p.number for p in self.pages if p.method == method]

        return {
            "page_count": self.page_count,
            "text_pages": len(numbers("text")),
            "ocr_pages": numbers("ocr"),
            "empty_pages": numbers("empty"),
            "ocr_skipped_pages": numbers("ocr_unavailable"),
            "characters": self.total_chars,
            "warnings": self.warnings,
        }


def normalise_text(text: str) -> str:
    """NFC-normalise and tidy whitespace without destroying Indic combining marks."""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("­", "")
    text = _HYPHEN_BREAK.sub("", text)
    lines = [_SPACE_BEFORE_INDIC_MARK.sub("", _SPACES.sub(" ", line)).strip() for line in text.split("\n")]
    return "\n".join(lines).strip()


def _block_to_paragraph(raw: str) -> str:
    """Join the visual lines of a block into one paragraph."""
    text = normalise_text(raw)
    return re.sub(r"\s*\n\s*", " ", text).strip()


def _page_blocks(page: pymupdf.Page) -> list[str]:
    blocks = page.get_text("blocks", sort=True, flags=pymupdf.TEXTFLAGS_TEXT & ~pymupdf.TEXT_PRESERVE_IMAGES)
    paragraphs: list[str] = []
    for block in blocks:
        # (x0, y0, x1, y1, text, block_no, block_type); type 0 is text.
        if block[6] != 0:
            continue
        paragraph = _block_to_paragraph(block[4])
        if paragraph:
            paragraphs.append(paragraph)
    return paragraphs


def _ocr_page(page: pymupdf.Page, *, tesseract_cmd: str, languages: str, dpi: int) -> list[str]:
    from PIL import Image

    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY, alpha=False)
    image = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    text = ocr_image(image, tesseract_cmd=tesseract_cmd, languages=languages)
    text = normalise_text(text)
    return [re.sub(r"\s*\n\s*", " ", para).strip() for para in _BLANK_LINES.split(text) if para.strip()]


def extract_pdf(
    path: Path,
    *,
    ocr_enabled: bool = True,
    tesseract_cmd: str = "",
    ocr_languages: str = "eng",
    ocr_dpi: int = 300,
    ocr_min_text_chars: int = 25,
    max_pages: int = 2000,
) -> ExtractionResult:
    try:
        doc = pymupdf.open(path)
    except Exception as exc:  # noqa: BLE001 - MuPDF raises several types for corrupt files
        raise ExtractionError("The PDF could not be opened. It may be damaged or not a real PDF.") from exc

    with doc:
        if doc.needs_pass:
            raise ExtractionError("The PDF is password-protected. Upload an unencrypted copy.")
        if doc.page_count == 0:
            raise ExtractionError("The PDF has no pages.")
        if doc.page_count > max_pages:
            raise ExtractionError(f"The PDF has {doc.page_count} pages; the limit is {max_pages}.")

        result = ExtractionResult(pages=[])
        ocr_ready = ocr_enabled and ocr_status(tesseract_cmd, ocr_languages).available
        ocr_message_added = False

        for index in range(doc.page_count):
            number = index + 1
            try:
                page = doc.load_page(index)
                blocks = _page_blocks(page)
            except Exception:  # noqa: BLE001
                logger.warning("Page %d could not be parsed; continuing", number, exc_info=True)
                result.warnings.append(f"Page {number} could not be parsed.")
                result.pages.append(PageText(number, [], "empty"))
                continue

            if sum(len(b) for b in blocks) >= ocr_min_text_chars:
                result.pages.append(PageText(number, blocks, "text"))
                continue

            # Too little text: likely scanned or image-only.
            has_images = bool(page.get_images(full=False))
            if not has_images and not blocks:
                result.pages.append(PageText(number, [], "empty"))
                continue
            if not ocr_ready:
                if not ocr_message_added:
                    status = ocr_status(tesseract_cmd, ocr_languages)
                    reason = "OCR is disabled (OCR_ENABLED=false)." if not ocr_enabled else status.message
                    result.warnings.append(f"Some pages look scanned but were not OCR'd: {reason}")
                    ocr_message_added = True
                result.pages.append(PageText(number, blocks, "ocr_unavailable" if not blocks else "text"))
                continue
            try:
                ocr_blocks = _ocr_page(page, tesseract_cmd=tesseract_cmd, languages=ocr_languages, dpi=ocr_dpi)
            except OcrUnavailableError as exc:
                result.warnings.append(exc.message)
                result.pages.append(PageText(number, blocks, "ocr_unavailable"))
                continue
            except Exception:  # noqa: BLE001
                logger.warning("OCR failed on page %d", number, exc_info=True)
                result.warnings.append(f"OCR failed on page {number}.")
                result.pages.append(PageText(number, blocks, "ocr_unavailable"))
                continue
            result.pages.append(PageText(number, ocr_blocks or blocks, "ocr" if ocr_blocks else "empty"))

        status = ocr_status(tesseract_cmd, ocr_languages)
        if ocr_ready and status.missing_languages and any(p.method == "ocr" for p in result.pages):
            result.warnings.append(status.message or "")
    return result
