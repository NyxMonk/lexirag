"""Local file storage for uploaded documents.

Files live under ``<storage_dir>/documents/<workspace_id>/<uuid>.pdf``. Client
supplied filenames never touch the filesystem; they are stored as metadata only.
"""

import logging
import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from app.core.errors import InvalidUploadError, PayloadTooLargeError

logger = logging.getLogger("lexirag.storage")

PDF_MAGIC = b"%PDF-"
CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class StoredFile:
    stored_filename: str
    relative_path: str  # POSIX-style, relative to the storage root
    size: int


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _workspace_dir(self, workspace_id: uuid.UUID) -> Path:
        return self.root / "documents" / str(workspace_id)

    def resolve(self, relative_path: str) -> Path:
        """Map a stored relative path to disk, refusing anything outside the root."""
        candidate = (self.root / relative_path).resolve()
        if not candidate.is_relative_to(self.root):
            raise InvalidUploadError("Refusing to access a path outside storage.")
        return candidate

    def save_pdf(self, source: BinaryIO, workspace_id: uuid.UUID, max_bytes: int) -> StoredFile:
        target_dir = self._workspace_dir(workspace_id)
        target_dir.mkdir(parents=True, exist_ok=True)

        stored_filename = f"{uuid.uuid4().hex}.pdf"
        final_path = target_dir / stored_filename
        temp_path = target_dir / f".{stored_filename}.part"

        size = 0
        try:
            with temp_path.open("wb") as out:
                first = source.read(CHUNK_SIZE)
                if not first.startswith(PDF_MAGIC):
                    raise InvalidUploadError("The file is not a valid PDF document.")
                chunk = first
                while chunk:
                    size += len(chunk)
                    if size > max_bytes:
                        raise PayloadTooLargeError(
                            f"File exceeds the {max_bytes // (1024 * 1024)} MB upload limit."
                        )
                    out.write(chunk)
                    chunk = source.read(CHUNK_SIZE)
            os.replace(temp_path, final_path)
        except BaseException:
            temp_path.unlink(missing_ok=True)
            raise

        relative = final_path.relative_to(self.root).as_posix()
        return StoredFile(stored_filename=stored_filename, relative_path=relative, size=size)

    def delete(self, relative_path: str) -> bool:
        try:
            path = self.resolve(relative_path)
            path.unlink(missing_ok=True)
            return True
        except OSError:
            logger.exception("Could not delete stored file %s", relative_path)
            return False

    def delete_workspace_dir(self, workspace_id: uuid.UUID) -> None:
        shutil.rmtree(self._workspace_dir(workspace_id), ignore_errors=True)
