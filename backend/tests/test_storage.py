"""Unit tests that do not require a database."""

import io
import uuid
from pathlib import Path

import pytest

from app.core.errors import InvalidUploadError, PayloadTooLargeError
from app.services.documents import sanitize_filename, validate_upload
from app.services.storage import LocalStorage


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("report.pdf", "report.pdf"),
        ("../../etc/passwd.pdf", "passwd.pdf"),
        ("C:\\Users\\x\\file.pdf", "file.pdf"),
        ("bad\x00name\x1f.pdf", "badname.pdf"),
        ("", "document.pdf"),
        (None, "document.pdf"),
        ("..", "document.pdf"),
        ("ਪੰਜਾਬ ਕਾਨੂੰਨ.pdf", "ਪੰਜਾਬ ਕਾਨੂੰਨ.pdf"),
    ],
)
def test_sanitize_filename(raw: str | None, expected: str) -> None:
    assert sanitize_filename(raw) == expected


def test_sanitize_filename_truncates_but_keeps_extension() -> None:
    name = sanitize_filename("a" * 400 + ".pdf")
    assert len(name) == 255 and name.endswith(".pdf")


def test_validate_upload() -> None:
    validate_upload("a.PDF", "application/pdf")
    validate_upload("a.pdf", "application/octet-stream")
    with pytest.raises(InvalidUploadError):
        validate_upload("a.docx", "application/pdf")
    with pytest.raises(InvalidUploadError):
        validate_upload("a.pdf", "text/html")


def test_storage_save_and_delete(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    ws = uuid.uuid4()
    stored = storage.save_pdf(io.BytesIO(b"%PDF-1.7 body"), ws, max_bytes=1024)
    path = storage.resolve(stored.relative_path)
    assert path.read_bytes() == b"%PDF-1.7 body"
    assert stored.relative_path.startswith(f"documents/{ws}/")
    assert storage.delete(stored.relative_path)
    assert not path.exists()


def test_storage_cleans_up_on_size_overflow(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    ws = uuid.uuid4()
    with pytest.raises(PayloadTooLargeError):
        storage.save_pdf(io.BytesIO(b"%PDF-" + b"x" * 2048), ws, max_bytes=1024)
    assert list((tmp_path / "documents" / str(ws)).iterdir()) == []


def test_storage_refuses_paths_outside_root(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path / "root")
    with pytest.raises(InvalidUploadError):
        storage.resolve("../outside.pdf")
