from pydantic import BaseModel


class DatabaseHealth(BaseModel):
    status: str
    pgvector: bool
    pgvector_version: str | None = None


class HealthResponse(BaseModel):
    status: str
    version: str
    database: DatabaseHealth


class Language(BaseModel):
    code: str
    name: str
    native_name: str
    script: str


class ModelProviderInfo(BaseModel):
    provider: str
    model: str | None
    # Whether credentials are present. The secret itself is never returned.
    configured: bool


class SystemInfo(BaseModel):
    name: str
    version: str
    environment: str
    supported_languages: list[Language]
    accepted_mime_types: list[str]
    max_upload_size_bytes: int
    model_provider: ModelProviderInfo
    retrieval_engine_available: bool
    answering_available: bool


class LanguagesResponse(BaseModel):
    languages: list[Language]
    ocr_language_packs: dict[str, str]


class LocalModelInfo(BaseModel):
    model: str
    enabled: bool
    downloaded: bool
    loaded: bool
    device: str | None
    dimension: int | None = None


class OcrInfo(BaseModel):
    enabled: bool
    available: bool
    version: str | None
    installed_languages: list[str]
    missing_languages: list[str]
    message: str | None


class RetrievalSettings(BaseModel):
    dense_top_k: int
    bm25_top_k: int
    rrf_k: int
    rerank_candidates: int
    final_top_k: int
    chunk_target_tokens: int
    chunk_overlap_tokens: int


class ModelsResponse(BaseModel):
    embedding: LocalModelInfo
    reranker: LocalModelInfo
    generation: ModelProviderInfo
    ocr: OcrInfo
    retrieval: RetrievalSettings
    models_allow_download: bool
    processing_queue: int
