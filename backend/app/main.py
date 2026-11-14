import logging
import re
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.database.session import check_database

logger = logging.getLogger("lexirag")
_REQUEST_ID_RE = re.compile(r"[A-Za-z0-9._-]{1,64}")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    settings.storage_path.mkdir(parents=True, exist_ok=True)
    db = check_database()
    if db["status"] != "ok":
        logger.warning("Database is not reachable at startup (%s).", db.get("error"))
    elif not db["pgvector"]:
        logger.warning("pgvector extension is missing. Run `alembic upgrade head`.")
    else:
        from app.services.processing import recover_interrupted

        recover_interrupted()
    from app.services.warmup import start_warmup

    start_warmup()
    logger.info("LexiRAG API %s ready. Storage: %s", __version__, settings.storage_path)
    yield
    from app.services.processing import queue

    queue.shutdown(wait=False)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="LexiRAG API",
        description="Multilingual legal document intelligence — local API.",
        version=__version__,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def request_log(request: Request, call_next) -> Response:
        # Accept a caller's request id only if it is short and plain; it is echoed in a header and logs.
        supplied = request.headers.get("x-request-id", "")
        request_id = supplied if _REQUEST_ID_RE.fullmatch(supplied) else uuid.uuid4().hex[:12]
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "%s %s -> %d (%.1f ms) [%s]",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            request_id,
        )
        return response

    register_exception_handlers(app)
    app.include_router(api_router, prefix="/api/v1")

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {"name": "LexiRAG API", "version": __version__, "docs": "/docs"}

    return app


app = create_app()
