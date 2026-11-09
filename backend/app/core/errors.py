"""Structured error responses.

Every error leaves the API in the same envelope::

    {"error": {"code": "not_found", "message": "...", "details": ...}}
"""

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("lexirag.errors")


class AppError(Exception):
    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "bad_request"

    def __init__(self, message: str, *, details: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class InvalidUploadError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "invalid_upload"


class PayloadTooLargeError(AppError):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    code = "payload_too_large"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


class InvalidRequestError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "invalid_request"


# RAG engine errors -> (HTTP status, error code)
def _rag_error_mapping() -> dict[type, tuple[int, str]]:
    from app.rag import errors as rag

    return {
        rag.LLMNotConfiguredError: (status.HTTP_503_SERVICE_UNAVAILABLE, "llm_not_configured"),
        rag.ModelUnavailableError: (status.HTTP_503_SERVICE_UNAVAILABLE, "model_unavailable"),
        rag.LLMProviderError: (status.HTTP_502_BAD_GATEWAY, "generation_failed"),
        rag.OcrUnavailableError: (status.HTTP_503_SERVICE_UNAVAILABLE, "ocr_unavailable"),
        rag.ExtractionError: (status.HTTP_422_UNPROCESSABLE_ENTITY, "extraction_failed"),
    }


def _envelope(status_code: int, code: str, message: str, details: Any = None) -> JSONResponse:
    body: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        body["details"] = details
    return JSONResponse(status_code=status_code, content={"error": body})


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return _envelope(exc.status_code, exc.code, exc.message, exc.details)

    from app.rag.errors import RagError

    mapping = _rag_error_mapping()

    @app.exception_handler(RagError)
    async def _rag_error(_: Request, exc: RagError) -> JSONResponse:
        for cls in type(exc).__mro__:
            if cls in mapping:
                status_code, code = mapping[cls]
                return _envelope(status_code, code, exc.message)
        return _envelope(500, "rag_error", exc.message)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"field": ".".join(str(p) for p in err["loc"][1:]), "message": err["msg"]}
            for err in exc.errors()
        ]
        return _envelope(422, "validation_error", "The request is invalid.", details)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = "not_found" if exc.status_code == 404 else "http_error"
        return _envelope(exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return _envelope(500, "internal_error", "An unexpected error occurred.")
