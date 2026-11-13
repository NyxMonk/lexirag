"""Environment-based configuration.

Values are read from process environment variables first, then from the
project-root ``.env`` file. Variable names are shared with the setup/start
scripts and docker-compose.yml, so keep them in sync with ``.env.example``.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url

# backend/app/core/config.py -> project root is three levels above ``app``.
BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_DIR.parent

LLMProvider = Literal["none", "ollama", "anthropic", "gemini"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    log_level: str = "INFO"

    # Database
    postgres_host: str = "127.0.0.1"
    postgres_port: int = 5433
    postgres_db: str = "lexirag"
    postgres_user: str = "lexirag"
    postgres_password: SecretStr = SecretStr("")
    # Optional full override, e.g. postgresql+psycopg://user:pass@host:5432/db
    database_url: SecretStr | None = None

    # HTTP
    backend_host: str = "127.0.0.1"
    backend_port: int = 8000
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Storage
    storage_dir: Path = Path("storage")
    max_upload_size_mb: int = 50

    # Document processing
    auto_process_uploads: bool = True
    ocr_enabled: bool = True
    # Full path to the tesseract executable when it is not on PATH.
    tesseract_cmd: str = ""
    ocr_languages: str = "eng+hin+ben+mar+pan+fra"
    ocr_dpi: int = 300
    # Pages with fewer extractable characters than this are treated as scanned.
    ocr_min_text_chars: int = 25
    max_pages: int = 2000

    # Chunking (token counts use the embedding model's tokenizer)
    chunk_target_tokens: int = 700
    chunk_overlap_tokens: int = 120
    chunk_min_tokens: int = 120

    # Models
    # Hugging Face cache directory. Empty uses the default (~/.cache/huggingface).
    model_cache_dir: str = ""
    # When false, models must be fetched beforehand with `python -m app.cli download-models`.
    models_allow_download: bool = False
    model_device: str = "auto"  # auto | cpu | cuda | mps
    embedding_model: str = "BAAI/bge-m3"
    embedding_dimension: int = 1024
    embedding_batch_size: int = 8
    embedding_max_tokens: int = 1024
    reranker_enabled: bool = True
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    reranker_max_tokens: int = 1024
    reranker_batch_size: int = 8

    # Retrieval
    retrieval_dense_top_k: int = 30
    retrieval_bm25_top_k: int = 30
    retrieval_rrf_k: int = 60
    rerank_candidates: int = 16
    retrieval_final_top_k: int = 6
    # Context budget (approximate tokens) for document summaries; longer documents are sampled.
    summary_max_tokens: int = 12000

    # Generation
    llm_provider: LLMProvider = "none"
    llm_temperature: float = 0.1
    llm_max_output_tokens: int = 4096
    llm_timeout_seconds: float = 120.0
    # Optional file replacing the built-in grounded-answer system prompt.
    llm_system_prompt_path: str = ""
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = ""
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-opus-5-5"
    # Thinking depth for Anthropic models (low | medium | high | xhigh | max).
    anthropic_effort: str = "medium"
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-3.5-flash"
    # Gemini thinking depth (minimal | low | medium | high); blank uses the model default. Lower is faster.
    gemini_thinking_level: str = "low"

    @field_validator("database_url", "anthropic_api_key", "gemini_api_key", mode="before")
    @classmethod
    def _blank_to_none(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("llm_provider", mode="before")
    @classmethod
    def _normalise_provider(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip().lower()
            return value or "none"
        return value

    @property
    def sqlalchemy_url(self) -> URL:
        if self.database_url is not None:
            url = make_url(self.database_url.get_secret_value())
            # Normalise plain postgres URLs onto the psycopg 3 driver.
            if url.drivername in ("postgres", "postgresql"):
                url = url.set(drivername="postgresql+psycopg")
            return url
        return URL.create(
            "postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def storage_path(self) -> Path:
        path = self.storage_dir
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path.resolve()

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def model_cache_path(self) -> str | None:
        if not self.model_cache_dir.strip():
            return None
        path = Path(self.model_cache_dir)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return str(path.resolve())

    @property
    def llm_model(self) -> str | None:
        return {
            "ollama": self.ollama_model,
            "anthropic": self.anthropic_model,
            "gemini": self.gemini_model,
        }.get(self.llm_provider) or None

    @property
    def llm_configured(self) -> bool:
        if self.llm_provider == "ollama":
            return bool(self.ollama_model and self.ollama_base_url)
        if self.llm_provider == "anthropic":
            return self.anthropic_api_key is not None and bool(self.anthropic_model)
        if self.llm_provider == "gemini":
            return self.gemini_api_key is not None and bool(self.gemini_model)
        return False


@lru_cache
def get_settings() -> Settings:
    return Settings()
