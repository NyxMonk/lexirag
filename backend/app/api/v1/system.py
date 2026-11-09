from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app import __version__
from app.api.deps import AppSettings
from app.core.languages import SUPPORTED_LANGUAGES
from app.database.session import check_database
from app.rag.model_store import model_is_downloaded
from app.rag.ocr import TESSERACT_LANGS, ocr_status
from app.schemas.system import (
    HealthResponse,
    LanguagesResponse,
    LocalModelInfo,
    ModelProviderInfo,
    ModelsResponse,
    OcrInfo,
    RetrievalSettings,
    SystemInfo,
)
from app.services.documents import PDF_MIME_TYPES

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse, responses={503: {"model": HealthResponse}})
def health() -> JSONResponse:
    database = check_database()
    healthy = database["status"] == "ok"
    body = HealthResponse(
        status="ok" if healthy else "degraded", version=__version__, database=database
    )
    return JSONResponse(status_code=200 if healthy else 503, content=body.model_dump())


def _provider_info(settings: AppSettings) -> ModelProviderInfo:
    return ModelProviderInfo(
        provider=settings.llm_provider, model=settings.llm_model, configured=settings.llm_configured
    )


@router.get("/system/info", response_model=SystemInfo)
def system_info(settings: AppSettings) -> SystemInfo:
    retrieval_ready = model_is_downloaded(settings.embedding_model, settings)
    return SystemInfo(
        name="LexiRAG",
        version=__version__,
        environment=settings.app_env,
        supported_languages=SUPPORTED_LANGUAGES,
        accepted_mime_types=sorted(PDF_MIME_TYPES),
        max_upload_size_bytes=settings.max_upload_size_bytes,
        model_provider=_provider_info(settings),
        retrieval_engine_available=retrieval_ready,
        answering_available=retrieval_ready and settings.llm_configured,
    )


@router.get("/settings/languages", response_model=LanguagesResponse, tags=["settings"])
def languages() -> LanguagesResponse:
    return LanguagesResponse(languages=SUPPORTED_LANGUAGES, ocr_language_packs=TESSERACT_LANGS)


@router.get("/settings/models", response_model=ModelsResponse, tags=["settings"])
def models(settings: AppSettings) -> ModelsResponse:
    """Model, OCR and retrieval configuration. Never includes credentials."""
    from app.rag import embeddings, reranking
    from app.services.processing import queue_depth

    embedder = embeddings._instance  # noqa: SLF001 - report state without forcing a load
    reranker = reranking._instance  # noqa: SLF001
    ocr = ocr_status(settings.tesseract_cmd, settings.ocr_languages)
    return ModelsResponse(
        embedding=LocalModelInfo(
            model=settings.embedding_model,
            enabled=True,
            downloaded=model_is_downloaded(settings.embedding_model, settings),
            loaded=bool(embedder and embedder.loaded),
            device=getattr(embedder, "device", None),
            dimension=getattr(embedder, "dimension", None) or settings.embedding_dimension,
        ),
        reranker=LocalModelInfo(
            model=settings.reranker_model,
            enabled=settings.reranker_enabled,
            downloaded=model_is_downloaded(settings.reranker_model, settings),
            loaded=bool(reranker and getattr(reranker, "loaded", False)),
            device=getattr(reranker, "device", None),
        ),
        generation=_provider_info(settings),
        ocr=OcrInfo(
            enabled=settings.ocr_enabled,
            available=ocr.available,
            version=ocr.version,
            installed_languages=list(ocr.installed_languages),
            missing_languages=list(ocr.missing_languages),
            message=ocr.message,
        ),
        retrieval=RetrievalSettings(
            dense_top_k=settings.retrieval_dense_top_k,
            bm25_top_k=settings.retrieval_bm25_top_k,
            rrf_k=settings.retrieval_rrf_k,
            rerank_candidates=settings.rerank_candidates,
            final_top_k=settings.retrieval_final_top_k,
            chunk_target_tokens=settings.chunk_target_tokens,
            chunk_overlap_tokens=settings.chunk_overlap_tokens,
        ),
        models_allow_download=settings.models_allow_download,
        processing_queue=queue_depth(),
    )
