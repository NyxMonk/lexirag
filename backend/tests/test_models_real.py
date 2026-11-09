"""Tests with the real BAAI/bge-m3 embedder and BAAI/bge-reranker-v2-m3 reranker.

Skipped when the models are not downloaded (python -m app.cli download-models).
They load ~4.5 GB of weights and run on CPU, so expect about a minute.
Questions and documents are synthetic.
"""

import uuid

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.rag.model_store import model_is_downloaded

pytestmark = pytest.mark.models

_settings = get_settings()
if not model_is_downloaded(_settings.embedding_model, _settings):
    pytest.skip("BAAI/bge-m3 is not downloaded", allow_module_level=True)


@pytest.fixture(scope="module")
def embedder():
    from app.rag.embeddings import EmbeddingModel

    return EmbeddingModel(get_settings())


@pytest.fixture(scope="module")
def reranker():
    from app.rag.reranking import CrossEncoderReranker

    settings = get_settings()
    if not model_is_downloaded(settings.reranker_model, settings):
        pytest.skip("BAAI/bge-reranker-v2-m3 is not downloaded")
    return CrossEncoderReranker(settings)


TERMINATION_EN = "Either party may terminate this agreement by giving sixty (60) days' written notice."
RENT_EN = "The monthly rent is INR 25,000, payable on or before the 5th day of each month."
LAW_EN = "This agreement is governed by the laws of India. The courts at Pune have exclusive jurisdiction."


def test_dimension_normalisation_and_batching(embedder) -> None:
    vectors = embedder.embed_documents([TERMINATION_EN, RENT_EN, LAW_EN])
    assert vectors.shape == (3, 1024)
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=1e-3)
    single = embedder.embed_documents([RENT_EN])[0]
    assert np.allclose(single, vectors[1], atol=1e-4)  # batching does not change results
    assert embedder.device in ("cpu", "cuda", "mps")


@pytest.mark.parametrize(
    "question",
    [
        "How can the agreement be terminated?",  # en
        "इस समझौते को समाप्त करने की शर्तें क्या हैं?",  # hi
        "हा करार कसा संपुष्टात आणता येतो?",  # mr
        "এই চুক্তি কীভাবে বাতিল করা যায়?",  # bn
        "ਇਹ ਇਕਰਾਰਨਾਮਾ ਕਿਵੇਂ ਖਤਮ ਕੀਤਾ ਜਾ ਸਕਦਾ ਹੈ?",  # pa
        "Comment le contrat peut-il être résilié ?",  # fr
    ],
)
def test_query_to_english_passage_cross_lingual(embedder, question: str) -> None:
    passages = embedder.embed_documents([RENT_EN, LAW_EN, TERMINATION_EN])
    query = embedder.embed_query(question)
    similarities = passages @ query
    assert int(np.argmax(similarities)) == 2, similarities


def test_reranker_orders_cross_lingual_passages(reranker) -> None:
    scores = reranker.score("इस समझौते को समाप्त करने की शर्तें क्या हैं?", [RENT_EN, TERMINATION_EN, LAW_EN])
    assert int(np.argmax(scores)) == 1, scores


def test_disabled_reranker_returns_none(monkeypatch) -> None:
    from app.rag import reranking

    monkeypatch.setattr(get_settings(), "reranker_enabled", False)
    assert reranking.get_reranker() is None


def test_missing_model_reports_download_command(monkeypatch) -> None:
    from app.rag.errors import ModelUnavailableError
    from app.rag.model_store import resolve_model_path

    settings = get_settings().model_copy(update={"models_allow_download": False})
    with pytest.raises(ModelUnavailableError, match="download-models"):
        resolve_model_path("BAAI/this-model-does-not-exist", settings)


# ── end to end with real models (fake LLM) ──
@pytest.fixture
def real_models(embedder, monkeypatch):
    from app.rag import embeddings
    from app.services import processing

    embeddings.set_embedding_model(embedder)
    monkeypatch.setattr(processing.queue, "submit", processing.run_pipeline)
    yield embedder
    embeddings.set_embedding_model(None)


def _ingest(client: TestClient, workspace_id: str, fixture_pdf, name: str) -> dict:
    doc = client.post(
        "/api/v1/documents/upload",
        data={"workspace_id": workspace_id},
        files={"file": (name, fixture_pdf(name), "application/pdf")},
    ).json()
    assert client.post(f"/api/v1/documents/{doc['id']}/process").status_code == 202
    status = client.get(f"/api/v1/documents/{doc['id']}/status").json()
    assert status["processing_status"] == "completed", status
    return doc


# (question, fixture holding the answer, page, text in the top passage, scope_to_document)
# Several synthetic documents share topics (rent, deposit, termination), so questions that are
# ambiguous across documents are scoped to their document, as a user would select it in the UI.
CROSS_LINGUAL_CASES = [
    ("What is the notice period for terminating the lease?", "synthetic_lease_en.pdf", 3, "sixty (60) days", True),
    ("इस समझौते को समाप्त करने की शर्तें क्या हैं?", "synthetic_lease_en.pdf", 3, "terminate", True),
    ("Quel est le délai de préavis pour résilier le bail ?", "synthetic_lease_en.pdf", 3, "terminate", True),
    ("How much security deposit did the tenant pay?", "synthetic_tenancy_hi.pdf", 2, "जमानत राशि", True),
    ("How many days of notice end the tenancy?", "synthetic_tenancy_hi.pdf", 2, "तीस दिन", True),
    ("কর্মচারী বছরে কত দিনের ছুটি পাবেন?", "synthetic_employment_bn.pdf", 1, "ছুটি", False),
    ("कर्मचारी को साल में कितने दिन की छुट्टी मिलती है?", "synthetic_employment_bn.pdf", 1, "ছুটি", False),
    ("How much earnest money (bayana) does the buyer pay for the land?", "synthetic_sale_pa.pdf", 1, "ਬਿਆਨਾ", False),
]


def test_cross_lingual_hybrid_retrieval_end_to_end(client, fixture_pdf, real_models, reranker, monkeypatch) -> None:
    from app.rag import reranking

    monkeypatch.setattr(get_settings(), "reranker_enabled", True)
    reranking.set_reranker(reranker)
    try:
        workspace = client.post("/api/v1/workspaces", json={"name": "Multilingual"}).json()
        docs = {
            name: _ingest(client, workspace["id"], fixture_pdf, name)
            for name in {case[1] for case in CROSS_LINGUAL_CASES}
        }
        failures = []
        for question, name, page, needle, scoped in CROSS_LINGUAL_CASES:
            payload = {"workspace_id": workspace["id"], "query": question, "top_k": 3}
            if scoped:
                payload["document_ids"] = [docs[name]["id"]]
            body = client.post("/api/v1/search", json=payload).json()
            top = body["retrieval"]["passages"][0]
            ok = (
                top["document_id"] == docs[name]["id"]
                and top["page_start"] <= page <= top["page_end"]
                and needle in top["content"]
                and body["retrieval"]["reranked"]
            )
            if not ok:
                failures.append((question, top["document_name"], top["page_start"], top["content"][:80]))
        assert not failures, failures
    finally:
        reranking.set_reranker(None)


def test_hindi_document_language_and_chunks(client, workspace, fixture_pdf, real_models) -> None:
    doc = _ingest(client, workspace["id"], fixture_pdf, "synthetic_tenancy_hi.pdf")
    chunks = client.get(f"/api/v1/documents/{doc['id']}/chunks").json()["items"]
    assert all(c["language"] == "hi" for c in chunks)
    assert any(c["section_title"] and c["section_title"].startswith("धारा") for c in chunks)
    # Real tokenizer counts (XLM-R SentencePiece), within the configured target.
    assert all(0 < c["token_count"] <= get_settings().chunk_target_tokens for c in chunks)
    assert uuid.UUID(chunks[0]["id"])
