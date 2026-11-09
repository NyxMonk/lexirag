"""Test configuration.

Database tests run against a dedicated ``<POSTGRES_DB>_test`` database on the
same PostgreSQL server as development (the Docker Compose container). It is
created and migrated automatically. Tests that need it are skipped, with a
clear reason, when the server is not reachable.
"""

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

# Configure the environment before any application module creates an engine.
from app.core.config import BACKEND_DIR, get_settings  # noqa: E402

_base_settings = get_settings()
_test_url = _base_settings.sqlalchemy_url.set(
    database=os.environ.get("LEXIRAG_TEST_DB", f"{_base_settings.postgres_db}_test")
)
_storage_dir = Path(tempfile.mkdtemp(prefix="lexirag-test-storage-"))

os.environ["DATABASE_URL"] = _test_url.render_as_string(hide_password=False)
os.environ["STORAGE_DIR"] = str(_storage_dir)
os.environ["MAX_UPLOAD_SIZE_MB"] = "1"
os.environ["LLM_PROVIDER"] = "none"
os.environ["GEMINI_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""
# Processing is triggered explicitly in tests; the real reranker is opted into per test.
os.environ["AUTO_PROCESS_UPLOADS"] = "false"
os.environ["RERANKER_ENABLED"] = "false"
os.environ["OCR_ENABLED"] = "false"
os.environ["CHUNK_TARGET_TOKENS"] = "120"
os.environ["CHUNK_OVERLAP_TOKENS"] = "20"
os.environ["CHUNK_MIN_TOKENS"] = "30"
get_settings.cache_clear()

FIXTURES = Path(__file__).parent / "fixtures"

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

MINIMAL_PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)


def _ensure_test_database() -> str | None:
    """Create and migrate the test database. Returns a skip reason on failure."""
    admin_url = _test_url.set(database=_base_settings.postgres_db)
    try:
        admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
        with admin.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": _test_url.database},
            ).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{_test_url.database}"'))
        admin.dispose()
    except Exception as exc:  # noqa: BLE001
        return f"PostgreSQL not reachable ({exc.__class__.__name__}). Start it with `docker compose up -d db`."

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")
    return None


_skip_reason = _ensure_test_database()


@pytest.fixture(scope="session")
def storage_dir() -> Path:
    return _storage_dir


@pytest.fixture
def client() -> Iterator[TestClient]:
    if _skip_reason:
        pytest.skip(_skip_reason)
    from app.database.session import engine
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client

    with engine.begin() as conn:
        conn.execute(text("TRUNCATE document_chunks, messages, conversations, documents, workspaces CASCADE"))


@pytest.fixture
def workspace(client: TestClient) -> dict:
    response = client.post("/api/v1/workspaces", json={"name": "Test matters"})
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def pdf_bytes() -> bytes:
    return MINIMAL_PDF


@pytest.fixture
def fixture_pdf():
    def load(name: str) -> bytes:
        return (FIXTURES / name).read_bytes()

    return load


@pytest.fixture
def fake_models():
    """Deterministic fake embedder (and no reranker) for pipeline and API tests."""
    from app.rag import embeddings
    from tests.fakes import FakeEmbeddingModel

    model = FakeEmbeddingModel()
    embeddings.set_embedding_model(model)
    yield model
    embeddings.set_embedding_model(None)


@pytest.fixture
def fake_llm():
    from app.rag import llm
    from tests.fakes import FakeLLM

    provider = FakeLLM()
    llm.set_llm_provider(provider)
    yield provider
    llm.set_llm_provider(None)
