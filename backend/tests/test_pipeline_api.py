"""Integration tests: upload -> process -> index -> search/answer, against PostgreSQL.

Uses the deterministic fake embedder and a scripted fake LLM, so the database,
pipeline, isolation and citation plumbing are tested without large models.
Documents are synthetic (see tests/fixtures/make_fixtures.py).
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.services import processing


@pytest.fixture
def sync_queue(monkeypatch):
    """Run queued processing inline so tests are deterministic."""
    monkeypatch.setattr(processing.queue, "submit", processing.run_pipeline)


def _upload(client: TestClient, workspace_id: str, name: str, data: bytes) -> dict:
    response = client.post(
        "/api/v1/documents/upload",
        data={"workspace_id": workspace_id},
        files={"file": (name, data, "application/pdf")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _process(client: TestClient, document_id: str, **body) -> dict:
    response = client.post(f"/api/v1/documents/{document_id}/process", json=body or None)
    assert response.status_code == 202, response.text
    return client.get(f"/api/v1/documents/{document_id}/status").json()


def _chunk_count(document_id: str) -> int:
    from app.database.session import SessionLocal
    from app.models import DocumentChunk

    with SessionLocal() as db:
        return db.scalar(select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id == uuid.UUID(document_id)))


def test_upload_process_index_and_status(client, workspace, fixture_pdf, fake_models, sync_queue) -> None:
    doc = _upload(client, workspace["id"], "lease.pdf", fixture_pdf("synthetic_lease_en.pdf"))
    assert doc["processing_status"] == "uploaded"

    status = _process(client, doc["id"])
    assert status["processing_status"] == "completed", status
    assert status["page_count"] == 3
    assert status["chunk_count"] >= 3
    assert status["detected_language"] == "en"
    assert status["processing_progress"] == {"done": status["chunk_count"], "total": status["chunk_count"]}
    assert status["extraction"]["text_pages"] == 3

    chunks = client.get(f"/api/v1/documents/{doc['id']}/chunks").json()
    assert chunks["total"] == status["chunk_count"]
    termination = [c for c in chunks["items"] if "sixty (60) days" in c["content"]]
    assert termination and termination[0]["page_start"] == 3
    assert termination[0]["section_title"] == "Clause 9 - Termination"
    assert all(c["language"] == "en" for c in chunks["items"])

    page3 = client.get(f"/api/v1/documents/{doc['id']}/chunks", params={"page": 3}).json()
    assert page3["total"] >= 1 and all(c["page_start"] <= 3 <= c["page_end"] for c in page3["items"])
    single = client.get(f"/api/v1/documents/{doc['id']}/chunks/{termination[0]['id']}")
    assert single.status_code == 200


def test_processing_is_idempotent_and_guarded(client, workspace, fixture_pdf, fake_models, sync_queue) -> None:
    doc = _upload(client, workspace["id"], "lease.pdf", fixture_pdf("synthetic_lease_en.pdf"))
    first = _process(client, doc["id"])
    count = _chunk_count(doc["id"])
    assert count == first["chunk_count"]

    again = client.post(f"/api/v1/documents/{doc['id']}/process")
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "conflict"

    forced = _process(client, doc["id"], force=True)
    assert forced["processing_status"] == "completed"
    assert _chunk_count(doc["id"]) == count  # replaced, not duplicated

    retry = client.post(f"/api/v1/documents/{doc['id']}/retry")
    assert retry.status_code == 409  # only failed documents can be retried


def test_in_progress_document_cannot_be_claimed_twice(client, workspace, fixture_pdf, fake_models, monkeypatch) -> None:
    submitted = []
    monkeypatch.setattr(processing.queue, "submit", submitted.append)
    doc = _upload(client, workspace["id"], "lease.pdf", fixture_pdf("synthetic_lease_en.pdf"))
    assert client.post(f"/api/v1/documents/{doc['id']}/process").status_code == 202
    assert client.get(f"/api/v1/documents/{doc['id']}/status").json()["processing_status"] == "queued"
    second = client.post(f"/api/v1/documents/{doc['id']}/process", json={"force": True})
    assert second.status_code == 409
    assert len(submitted) == 1


def test_failed_processing_records_error_and_can_be_retried(client, workspace, fixture_pdf, fake_models, sync_queue) -> None:
    doc = _upload(client, workspace["id"], "scan.pdf", fixture_pdf("synthetic_scanned_en.pdf"))
    status = _process(client, doc["id"])
    assert status["processing_status"] == "failed"
    assert "No text could be extracted" in status["processing_error"]
    assert "OCR" in status["processing_error"]
    assert status["extraction"] is None or status["extraction"]["ocr_skipped_pages"] == [1]

    retry = client.post(f"/api/v1/documents/{doc['id']}/retry")
    assert retry.status_code == 202
    assert client.get(f"/api/v1/documents/{doc['id']}/status").json()["processing_status"] == "failed"


def test_auto_processing_on_upload(client, workspace, fixture_pdf, fake_models, sync_queue, monkeypatch) -> None:
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "auto_process_uploads", True)
    doc = _upload(client, workspace["id"], "hi.pdf", fixture_pdf("synthetic_tenancy_hi.pdf"))
    status = client.get(f"/api/v1/documents/{doc['id']}/status").json()
    assert status["processing_status"] == "completed"
    assert status["detected_language"] == "hi"


def test_language_override(client, workspace, fixture_pdf, fake_models, sync_queue) -> None:
    doc = _upload(client, workspace["id"], "mr.pdf", fixture_pdf("synthetic_lease_mr.pdf"))
    _process(client, doc["id"])
    detected = client.get(f"/api/v1/documents/{doc['id']}").json()
    assert detected["detected_language"] == "mr" and detected["effective_language"] == "mr"

    updated = client.patch(f"/api/v1/documents/{doc['id']}", json={"language_override": "hi"}).json()
    assert updated["effective_language"] == "hi" and updated["detected_language"] == "mr"
    assert client.patch(f"/api/v1/documents/{doc['id']}", json={"language_override": "ta"}).status_code == 422
    cleared = client.patch(f"/api/v1/documents/{doc['id']}", json={"language_override": None}).json()
    assert cleared["effective_language"] == "mr"


def test_delete_document_removes_chunks(client, workspace, fixture_pdf, fake_models, sync_queue) -> None:
    doc = _upload(client, workspace["id"], "lease.pdf", fixture_pdf("synthetic_lease_en.pdf"))
    _process(client, doc["id"])
    assert _chunk_count(doc["id"]) > 0
    assert client.delete(f"/api/v1/documents/{doc['id']}").status_code == 204
    assert _chunk_count(doc["id"]) == 0


def test_delete_workspace_removes_chunks(client, workspace, fixture_pdf, fake_models, sync_queue) -> None:
    doc = _upload(client, workspace["id"], "lease.pdf", fixture_pdf("synthetic_lease_en.pdf"))
    _process(client, doc["id"])
    assert client.delete(f"/api/v1/workspaces/{workspace['id']}").status_code == 204
    assert _chunk_count(doc["id"]) == 0


# ── retrieval ──
def _two_workspaces(client, fixture_pdf):
    a = client.post("/api/v1/workspaces", json={"name": "A"}).json()
    b = client.post("/api/v1/workspaces", json={"name": "B"}).json()
    lease = _upload(client, a["id"], "lease.pdf", fixture_pdf("synthetic_lease_en.pdf"))
    service = _upload(client, a["id"], "service.pdf", fixture_pdf("synthetic_injection_en.pdf"))
    other = _upload(client, b["id"], "other-lease.pdf", fixture_pdf("synthetic_lease_en.pdf"))
    for d in (lease, service, other):
        _process(client, d["id"])
    return a, b, lease, service, other


def test_search_is_hybrid_and_workspace_isolated(client, fixture_pdf, fake_models, sync_queue) -> None:
    a, b, lease, service, other = _two_workspaces(client, fixture_pdf)
    response = client.post(
        "/api/v1/search", json={"workspace_id": a["id"], "query": "terminate agreement written notice", "top_k": 5}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    passages = body["retrieval"]["passages"]
    assert passages, body
    assert {p["document_id"] for p in passages} <= {lease["id"], service["id"]}
    top = passages[0]
    assert top["document_id"] == lease["id"] and top["page_start"] == 3
    assert top["dense_rank"] is not None and top["bm25_rank"] is not None
    assert body["retrieval"]["reranked"] is False
    assert any("Reranking is disabled" in n for n in body["notes"])
    assert body["query_language"] == "en"

    scoped = client.post(
        "/api/v1/search",
        json={"workspace_id": a["id"], "query": "service fee invoice", "document_ids": [service["id"]]},
    ).json()
    assert {p["document_id"] for p in scoped["retrieval"]["passages"]} == {service["id"]}


def test_cross_workspace_document_ids_are_rejected(client, fixture_pdf, fake_models, sync_queue) -> None:
    a, b, lease, service, other = _two_workspaces(client, fixture_pdf)
    response = client.post(
        "/api/v1/search", json={"workspace_id": a["id"], "query": "rent", "document_ids": [other["id"]]}
    )
    assert response.status_code == 404
    assert other["id"] in response.json()["error"]["details"]["missing"]


def test_search_requires_processed_documents(client, workspace, fixture_pdf, fake_models) -> None:
    _upload(client, workspace["id"], "lease.pdf", fixture_pdf("synthetic_lease_en.pdf"))
    response = client.post("/api/v1/search", json={"workspace_id": workspace["id"], "query": "rent"})
    assert response.status_code == 422
    assert "no processed documents" in response.json()["error"]["message"]


def test_reranker_reorders_candidates(client, fixture_pdf, fake_models, sync_queue) -> None:
    from app.core.config import get_settings
    from app.rag.retrieval import HybridRetriever, RetrievalScope
    from app.database.session import SessionLocal

    class GoverningLawReranker:
        model_id = "fake-reranker"

        def score(self, query, passages):
            return [1.0 if "Governing Law" in p else 0.0 for p in passages]

    a, *_ = _two_workspaces(client, fixture_pdf)
    retriever = HybridRetriever(get_settings(), fake_models, GoverningLawReranker())
    with SessionLocal() as db:
        result = retriever.retrieve(db, "rent deposit termination law", RetrievalScope(uuid.UUID(a["id"])))
    assert result.reranked and result.reranker_model == "fake-reranker"
    assert "Governing Law" in result.chunks[0].content
    assert result.chunks[0].rerank_score == 1.0


# ── answering ──
def test_query_requires_configured_llm(client, workspace, fixture_pdf, fake_models, sync_queue) -> None:
    doc = _upload(client, workspace["id"], "lease.pdf", fixture_pdf("synthetic_lease_en.pdf"))
    _process(client, doc["id"])
    response = client.post("/api/v1/chat/query", json={"workspace_id": workspace["id"], "question": "What is the rent?"})
    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "llm_not_configured" and "LLM_PROVIDER" in error["message"]


def test_query_returns_grounded_citations(client, workspace, fixture_pdf, fake_models, fake_llm, sync_queue) -> None:
    doc = _upload(client, workspace["id"], "lease.pdf", fixture_pdf("synthetic_lease_en.pdf"))
    _process(client, doc["id"])
    fake_llm.queue(
        {
            "answer": "समझौता 60 दिन की लिखित सूचना देकर समाप्त किया जा सकता है [S1]। [S9]",
            "evidence_sufficient": True,
            "citations": [
                {"source_id": "S1", "quote": "Either party may terminate this agreement by giving sixty (60) days' written notice"},
                {"source_id": "S9", "quote": "invented"},
            ],
        }
    )
    response = client.post(
        "/api/v1/chat/query",
        # The fake embedder is lexical, so the question is English; the answer language is Hindi.
        json={
            "workspace_id": workspace["id"],
            "question": "Can either party terminate this agreement by written notice?",
            "response_language": "hi",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["query_language"] == "en" and body["language"] == "hi"
    assert body["answer"].startswith("समझौता 60 दिन") and "[1]" in body["answer"] and "S9" not in body["answer"]
    assert body["evidence_sufficient"] is True
    [citation] = body["citations"]
    assert citation["document_id"] == doc["id"] and citation["document_name"] == "lease.pdf"
    assert citation["quote_verified"] is True and citation["source_language"] == "en"
    # The cited chunk really is stored and its pages come from extraction metadata.
    stored = client.get(f"/api/v1/documents/{doc['id']}/chunks/{citation['chunk_id']}").json()
    assert citation["quoted_text"] in stored["content"]
    assert (citation["page_start"], citation["page_end"]) == (stored["page_start"], stored["page_end"])
    assert any("S9" in w for w in body["warnings"])

    system, user = fake_llm.prompts[-1]
    assert "untrusted" in system and "Answer language: Hindi (हिन्दी)" in user


def test_answer_without_citations_is_marked_unsupported(client, workspace, fixture_pdf, fake_models, fake_llm, sync_queue) -> None:
    doc = _upload(client, workspace["id"], "lease.pdf", fixture_pdf("synthetic_lease_en.pdf"))
    _process(client, doc["id"])
    fake_llm.queue({"answer": "The rent is zero.", "evidence_sufficient": True, "citations": []})
    body = client.post(
        "/api/v1/chat/query",
        json={"workspace_id": workspace["id"], "question": "What is the rent?", "response_language": "en"},
    ).json()
    assert body["evidence_sufficient"] is False
    assert body["citations"] == []
    assert any("cited no source" in w for w in body["warnings"])


def test_malformed_model_output_is_retried_then_reported(client, workspace, fixture_pdf, fake_models, fake_llm, sync_queue) -> None:
    doc = _upload(client, workspace["id"], "lease.pdf", fixture_pdf("synthetic_lease_en.pdf"))
    _process(client, doc["id"])
    fake_llm.queue("Sure! The rent is INR 25,000.")
    fake_llm.queue("Still not JSON")
    response = client.post("/api/v1/chat/query", json={"workspace_id": workspace["id"], "question": "Rent?"})
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "generation_failed"
    assert len(fake_llm.prompts) == 2


def test_conversation_persistence(client, workspace, fixture_pdf, fake_models, fake_llm, sync_queue) -> None:
    doc = _upload(client, workspace["id"], "lease.pdf", fixture_pdf("synthetic_lease_en.pdf"))
    _process(client, doc["id"])
    conversation = client.post("/api/v1/chat/conversations", json={"workspace_id": workspace["id"]}).json()

    first = client.post(
        f"/api/v1/chat/conversations/{conversation['id']}/messages",
        json={"content": "What is the security deposit?", "document_ids": [doc["id"]], "response_language": "fr"},
    )
    assert first.status_code == 201, first.text
    exchange = first.json()
    assert exchange["user_message"]["role"] == "user"
    assert exchange["assistant_message"]["role"] == "assistant"
    assert exchange["assistant_message"]["language"] == "fr"
    assert exchange["assistant_message"]["citations"][0]["document_id"] == doc["id"]

    client.post(f"/api/v1/chat/conversations/{conversation['id']}/messages", json={"content": "And the rent?"})
    detail = client.get(f"/api/v1/chat/conversations/{conversation['id']}").json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant", "user", "assistant"]
    assert detail["title"] == "What is the security deposit?"
    # Follow-up prompts include earlier turns as context (not as evidence).
    assert "Earlier conversation" in fake_llm.prompts[-1][1]

    listing = client.get("/api/v1/conversations", params={"workspace_id": workspace["id"]}).json()
    assert listing[0]["message_count"] == 4

    assert client.delete(f"/api/v1/chat/conversations/{conversation['id']}").status_code == 204
    assert client.get(f"/api/v1/chat/conversations/{conversation['id']}").status_code == 404


def test_failed_answer_does_not_persist_messages(client, workspace, fixture_pdf, fake_models, sync_queue) -> None:
    doc = _upload(client, workspace["id"], "lease.pdf", fixture_pdf("synthetic_lease_en.pdf"))
    _process(client, doc["id"])
    conversation = client.post("/api/v1/chat/conversations", json={"workspace_id": workspace["id"]}).json()
    response = client.post(f"/api/v1/chat/conversations/{conversation['id']}/messages", json={"content": "Rent?"})
    assert response.status_code == 503  # no LLM configured
    assert client.get(f"/api/v1/chat/conversations/{conversation['id']}").json()["messages"] == []


def test_settings_endpoints(client) -> None:
    languages = client.get("/api/v1/settings/languages").json()
    assert [l["code"] for l in languages["languages"]] == ["en", "hi", "bn", "mr", "pa", "fr"]
    assert languages["ocr_language_packs"]["pa"] == "pan"
    models = client.get("/api/v1/settings/models").json()
    assert models["embedding"]["model"] == "BAAI/bge-m3"
    assert models["generation"]["provider"] == "none" and models["generation"]["configured"] is False
    assert "api_key" not in str(models).lower()


def test_document_summary_cites_pages(client, workspace, fixture_pdf, fake_models, fake_llm, sync_queue) -> None:
    doc = _upload(client, workspace["id"], "lease.pdf", fixture_pdf("synthetic_lease_en.pdf"))
    _process(client, doc["id"])
    body = client.post(f"/api/v1/documents/{doc['id']}/summary", json={"response_language": "fr"}).json()
    assert body["language"] == "fr" and body["evidence_sufficient"] is True
    [citation] = body["citations"]
    stored = client.get(f"/api/v1/documents/{doc['id']}/chunks/{citation['chunk_id']}").json()
    assert citation["quote_verified"] and stored["page_start"] <= citation["quote_page"] <= stored["page_end"]
    user_prompt = fake_llm.prompts[-1][1]
    assert "Answer language: French" in user_prompt and "Summarise the document" in user_prompt
    # Every stored chunk of this short document is supplied (no sampling needed).
    assert user_prompt.count("<source id=") == client.get(f"/api/v1/documents/{doc['id']}/chunks").json()["total"]


def test_summary_rejects_unprocessed_and_unconfigured(client, workspace, fixture_pdf, fake_models, sync_queue) -> None:
    doc = _upload(client, workspace["id"], "lease.pdf", fixture_pdf("synthetic_lease_en.pdf"))
    assert client.post(f"/api/v1/documents/{doc['id']}/summary", json={}).status_code == 422
    _process(client, doc["id"])
    assert client.post(f"/api/v1/documents/{doc['id']}/summary", json={}).json()["error"]["code"] == "llm_not_configured"


def test_summary_sampling_respects_budget() -> None:
    from app.rag.answering import select_for_summary
    from app.rag.retrieval import RetrievedChunk

    chunks = [RetrievedChunk(uuid.uuid4(), uuid.uuid4(), "d.pdf", "x" * 3000, i + 1, i + 1, f"S{i // 3}", "en", i)
              for i in range(30)]
    kept, note = select_for_summary(chunks, 5000)
    assert sum(len(c.content) // 3 for c in kept) <= 5000 and note and "of 30 passages" in note
    assert [c.chunk_index for c in kept] == sorted(c.chunk_index for c in kept)
    assert select_for_summary(chunks[:2], 5000) == (sorted(chunks[:2], key=lambda c: c.chunk_index), None)


def test_new_conversation_is_created_only_on_success(client, workspace, fixture_pdf, fake_models, fake_llm, sync_queue, monkeypatch) -> None:
    from app.rag import llm

    doc = _upload(client, workspace["id"], "lease.pdf", fixture_pdf("synthetic_lease_en.pdf"))
    _process(client, doc["id"])
    listing = lambda: client.get("/api/v1/conversations", params={"workspace_id": workspace["id"]}).json()  # noqa: E731

    fake_llm.queue("not json"); fake_llm.queue("still not json")
    failed = client.post("/api/v1/chat/messages", json={"workspace_id": workspace["id"], "content": "Rent?"})
    assert failed.status_code == 502 and listing() == []  # nothing persisted

    ok = client.post("/api/v1/chat/messages", json={"workspace_id": workspace["id"], "content": "What is the rent?",
                                                    "response_language": "hi"})
    assert ok.status_code == 201, ok.text
    body = ok.json()
    [conversation] = listing()
    assert conversation["id"] == body["conversation_id"] and conversation["title"] == "What is the rent?"
    assert conversation["message_count"] == 2 and body["answer"]["language"] == "hi"

    other = client.post("/api/v1/workspaces", json={"name": "Other"}).json()
    cross = client.post("/api/v1/chat/messages", json={"workspace_id": other["id"], "content": "Rent?",
                                                       "document_ids": [doc["id"]]})
    assert cross.status_code == 404  # documents of another workspace are rejected
