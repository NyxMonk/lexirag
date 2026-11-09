"""Errors raised by the RAG engine. The API layer maps them to HTTP responses."""


class RagError(Exception):
    """Base class. ``message`` is safe to show to users (no paths or secrets)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ExtractionError(RagError):
    """The PDF could not be read (encrypted, malformed, or without any usable text)."""


class OcrUnavailableError(RagError):
    """Tesseract or a required language pack is not installed."""


class ModelUnavailableError(RagError):
    """A model is not downloaded, cannot be loaded, or does not match expectations."""


class LLMNotConfiguredError(RagError):
    """No generation provider is configured, or its credentials are missing."""


class LLMProviderError(RagError):
    """The generation provider failed (network, rate limit, refusal, malformed output)."""
