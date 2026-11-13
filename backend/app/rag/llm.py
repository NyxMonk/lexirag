"""Provider-independent text generation.

Each adapter takes a system prompt and a user prompt and returns raw model
text. Prompt construction and output validation live in ``answering``; adapters
never invent output. Missing configuration raises ``LLMNotConfiguredError`` with
the exact environment variables to set.
"""

import logging
import time
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import Settings, get_settings
from app.rag.errors import LLMNotConfiguredError, LLMProviderError

logger = logging.getLogger("lexirag.llm")


@dataclass
class Generation:
    text: str
    provider: str
    model: str
    duration_ms: float
    stop_reason: str | None = None


class LLMProvider(Protocol):
    name: str
    model: str

    def generate(self, system: str, user: str) -> Generation: ...


def _http_error(provider: str, exc: Exception) -> LLMProviderError:
    if isinstance(exc, httpx.TimeoutException):
        return LLMProviderError(f"{provider} did not respond in time. Try again, or raise LLM_TIMEOUT_SECONDS.")
    if isinstance(exc, httpx.ConnectError):
        return LLMProviderError(f"Cannot connect to {provider}. Check that it is running and reachable.")
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        detail = _provider_message(exc.response)
        if status in (401, 403):
            return LLMProviderError(f"{provider} rejected the credentials (HTTP {status}). Check the API key.")
        if status == 404:
            return LLMProviderError(
                f"{provider} does not offer the configured model (HTTP 404). Check the model name.{detail}"
            )
        if status == 429:
            return LLMProviderError(f"{provider} rate limit or quota reached (HTTP 429). Try again later.")
        if status in (500, 502, 503, 504):
            return LLMProviderError(f"{provider} is temporarily unavailable or overloaded (HTTP {status}). Try again.")
        return LLMProviderError(f"{provider} returned HTTP {status}.{detail}")
    return LLMProviderError(f"{provider} request failed: {exc.__class__.__name__}.")


RETRY_STATUSES = {429, 500, 502, 503, 504}
RETRY_DELAYS = (2.0, 6.0)  # seconds; at most two retries
MAX_RETRY_AFTER = 20.0


def _post_with_retry(client: httpx.Client, url: str, **kwargs) -> httpx.Response:
    """POST with bounded retries for rate limits and transient overloads."""
    for attempt in range(len(RETRY_DELAYS) + 1):
        response = client.post(url, **kwargs)
        if response.status_code not in RETRY_STATUSES or attempt == len(RETRY_DELAYS):
            break
        delay = RETRY_DELAYS[attempt]
        retry_after = response.headers.get("retry-after", "")
        if retry_after.replace(".", "", 1).isdigit():
            delay = min(max(delay, float(retry_after)), MAX_RETRY_AFTER)
        logger.info("Provider returned HTTP %d; retrying in %.0fs", response.status_code, delay)
        time.sleep(delay)
    response.raise_for_status()
    return response


def _provider_message(response: httpx.Response) -> str:
    """The provider's own error text (never contains our credentials), shortened."""
    try:
        data = response.json()
    except ValueError:
        return ""
    error = data.get("error") if isinstance(data, dict) else None
    message = error.get("message") if isinstance(error, dict) else error if isinstance(error, str) else None
    return f" Provider says: {str(message)[:200]}" if message else ""


class OllamaProvider:
    name = "ollama"

    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        self.settings = settings
        self.model = settings.ollama_model
        self._client = httpx.Client(
            base_url=settings.ollama_base_url.rstrip("/"), timeout=settings.llm_timeout_seconds, transport=transport
        )

    def generate(self, system: str, user: str) -> Generation:
        started = time.perf_counter()
        try:
            response = _post_with_retry(
                self._client,
                "/api/chat",
                json={
                    "model": self.model,
                    "stream": False,
                    "format": "json",
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                    "options": {
                        "temperature": self.settings.llm_temperature,
                        "num_predict": self.settings.llm_max_output_tokens,
                    },
                },
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise LLMProviderError(
                    f"Ollama has no model '{self.model}'. Pull it with: ollama pull {self.model}"
                ) from exc
            raise _http_error("Ollama", exc) from exc
        except httpx.HTTPError as exc:
            raise _http_error("Ollama", exc) from exc
        data = response.json()
        text = (data.get("message") or {}).get("content") or ""
        return Generation(text, self.name, self.model, (time.perf_counter() - started) * 1000, data.get("done_reason"))


class GeminiProvider:
    name = "gemini"
    base_url = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        self.settings = settings
        self.model = settings.gemini_model
        assert settings.gemini_api_key is not None
        self._key = settings.gemini_api_key.get_secret_value()
        self._client = httpx.Client(base_url=self.base_url, timeout=settings.llm_timeout_seconds, transport=transport)

    def _thinking_config(self) -> dict[str, object]:
        level = self.settings.gemini_thinking_level.strip().lower()
        return {"thinkingConfig": {"thinkingLevel": level}} if level else {}

    def generate(self, system: str, user: str) -> Generation:
        started = time.perf_counter()
        try:
            response = _post_with_retry(
                self._client,
                f"/models/{self.model}:generateContent",
                # Header, not query string, so the key never appears in URLs or logs.
                headers={"x-goog-api-key": self._key},
                json={
                    "systemInstruction": {"parts": [{"text": system}]},
                    "contents": [{"role": "user", "parts": [{"text": user}]}],
                    "generationConfig": {
                        "temperature": self.settings.llm_temperature,
                        "maxOutputTokens": self.settings.llm_max_output_tokens,
                        "responseMimeType": "application/json",
                        **self._thinking_config(),
                    },
                },
            )
        except httpx.HTTPError as exc:
            raise _http_error("Gemini", exc) from exc
        data = response.json()
        feedback = data.get("promptFeedback") or {}
        if feedback.get("blockReason"):
            raise LLMProviderError(f"Gemini blocked the request ({feedback['blockReason']}).")
        candidates = data.get("candidates") or []
        if not candidates:
            raise LLMProviderError("Gemini returned no answer.")
        candidate = candidates[0]
        parts = (candidate.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        finish = candidate.get("finishReason")
        if finish in ("SAFETY", "RECITATION", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII"):
            raise LLMProviderError(f"Gemini stopped the answer ({finish}).")
        return Generation(text, self.name, self.model, (time.perf_counter() - started) * 1000, finish)


class AnthropicProvider:
    """Claude via the official Anthropic SDK (Messages API)."""

    name = "anthropic"

    def __init__(self, settings: Settings, client: object | None = None) -> None:
        self.settings = settings
        self.model = settings.anthropic_model
        if client is None:
            import anthropic

            assert settings.anthropic_api_key is not None
            client = anthropic.Anthropic(
                api_key=settings.anthropic_api_key.get_secret_value(),
                timeout=settings.llm_timeout_seconds,
                max_retries=2,
            )
        self._client = client

    def generate(self, system: str, user: str) -> Generation:
        import anthropic

        started = time.perf_counter()
        try:
            response = self._client.beta.messages.create(  # type: ignore[attr-defined]
                model=self.model,
                # Adaptive thinking counts toward max_tokens; leave room for it.
                max_tokens=max(16000, self.settings.llm_max_output_tokens),
                system=system,
                messages=[{"role": "user", "content": user}],
                # Server-side fallback re-runs a declined request on another model inside the same call.
                betas=["server-side-fallback-2026-07-01"],
                extra_body={
                    "fallbacks": "default",
                    "output_config": {"effort": self.settings.anthropic_effort},
                },
            )
        except anthropic.AuthenticationError as exc:
            raise LLMProviderError("Anthropic rejected the API key (ANTHROPIC_API_KEY).") from exc
        except anthropic.PermissionDeniedError as exc:
            raise LLMProviderError("The Anthropic API key lacks permission for this model or feature.") from exc
        except anthropic.NotFoundError as exc:
            raise LLMProviderError(f"Anthropic does not know the model '{self.model}' (ANTHROPIC_MODEL).") from exc
        except anthropic.RateLimitError as exc:
            raise LLMProviderError("Anthropic rate limit reached. Try again shortly.") from exc
        except anthropic.APIStatusError as exc:
            raise LLMProviderError(f"Anthropic returned HTTP {exc.status_code}.") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMProviderError("Cannot connect to the Anthropic API.") from exc
        if response.stop_reason == "refusal":
            raise LLMProviderError("The model declined to answer this request.")
        text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
        return Generation(text, self.name, response.model, (time.perf_counter() - started) * 1000, response.stop_reason)


_PROVIDER_HELP = {
    "ollama": "Set OLLAMA_MODEL (and OLLAMA_BASE_URL if Ollama is not on http://localhost:11434), "
    "then pull the model with `ollama pull <model>`.",
    "anthropic": "Set ANTHROPIC_API_KEY (and optionally ANTHROPIC_MODEL).",
    "gemini": "Set GEMINI_API_KEY (and optionally GEMINI_MODEL).",
}

_cached: tuple[tuple, LLMProvider] | None = None


def get_llm_provider(settings: Settings | None = None) -> LLMProvider:
    global _cached
    settings = settings or get_settings()
    provider = settings.llm_provider
    if provider == "none":
        raise LLMNotConfiguredError(
            "No answer-generation provider is configured. Set LLM_PROVIDER to ollama, anthropic or gemini "
            "in .env and restart the backend."
        )
    if not settings.llm_configured:
        raise LLMNotConfiguredError(f"LLM_PROVIDER={provider} is incomplete. {_PROVIDER_HELP[provider]}")
    key = (provider, settings.llm_model, settings.ollama_base_url)
    if _cached and _cached[0] == key:
        return _cached[1]
    instance: LLMProvider
    if provider == "ollama":
        instance = OllamaProvider(settings)
    elif provider == "gemini":
        instance = GeminiProvider(settings)
    else:
        instance = AnthropicProvider(settings)
    _cached = (key, instance)
    return instance


def set_llm_provider(provider: LLMProvider | None) -> None:
    """Testing hook: force a provider (bypasses configuration checks)."""
    global _cached
    _cached = None if provider is None else (("override",), provider)


def overridden_provider() -> LLMProvider | None:
    return _cached[1] if _cached and _cached[0] == ("override",) else None
