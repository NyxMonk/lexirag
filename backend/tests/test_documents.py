import uuid

from fastapi.testclient import TestClient


def _upload(client: TestClient, workspace_id: str, name: str, data: bytes, mime: str = "application/pdf"):
    return client.post(
        "/api/v1/documents/upload",
        data={"workspace_id": workspace_id},
        files={"file": (name, data, mime)},
    )


def test_upload_persists_metadata_and_file(
    client: TestClient, workspace: dict, pdf_bytes: bytes, storage_dir
) -> None:
    response = _upload(client, workspace["id"], "Lease Agreement.pdf", pdf_bytes)
    assert response.status_code == 201
    doc = response.json()
    assert doc["original_filename"] == "Lease Agreement.pdf"
    assert doc["file_size"] == len(pdf_bytes)
    assert doc["mime_type"] == "application/pdf"
    # Phase 1 never claims processing happened.
    assert doc["processing_status"] == "uploaded"
    assert doc["detected_language"] is None
    assert "file_path" not in doc and "stored_filename" not in doc

    files = list((storage_dir / "documents" / workspace["id"]).iterdir())
    assert len(files) == 1 and files[0].read_bytes() == pdf_bytes

    fetched = client.get(f"/api/v1/documents/{doc['id']}")
    assert fetched.status_code == 200 and fetched.json()["id"] == doc["id"]

    raw = client.get(f"/api/v1/documents/{doc['id']}/file")
    assert raw.status_code == 200
    assert raw.headers["content-type"] == "application/pdf"
    assert raw.content == pdf_bytes


def test_upload_rejects_non_pdf_extension(client: TestClient, workspace: dict, pdf_bytes: bytes) -> None:
    response = _upload(client, workspace["id"], "notes.txt", pdf_bytes, "text/plain")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_upload"


def test_upload_rejects_disguised_file(client: TestClient, workspace: dict, storage_dir) -> None:
    response = _upload(client, workspace["id"], "evil.pdf", b"MZ\x90\x00 not a pdf")
    assert response.status_code == 422
    workspace_dir = storage_dir / "documents" / workspace["id"]
    # No partial or temporary files are left behind.
    assert not workspace_dir.exists() or not any(workspace_dir.iterdir())


def test_upload_rejects_wrong_mime(client: TestClient, workspace: dict, pdf_bytes: bytes) -> None:
    response = _upload(client, workspace["id"], "a.pdf", pdf_bytes, "image/png")
    assert response.status_code == 422


def test_upload_enforces_size_limit(client: TestClient, workspace: dict, pdf_bytes: bytes, storage_dir) -> None:
    oversized = pdf_bytes + b"0" * (1024 * 1024 + 10)  # limit is 1 MB in tests
    response = _upload(client, workspace["id"], "big.pdf", oversized)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"
    workspace_dir = storage_dir / "documents" / workspace["id"]
    assert not workspace_dir.exists() or not any(workspace_dir.iterdir())


def test_upload_to_missing_workspace(client: TestClient, pdf_bytes: bytes) -> None:
    response = _upload(client, str(uuid.uuid4()), "a.pdf", pdf_bytes)
    assert response.status_code == 404


def test_path_traversal_filename_is_neutralised(
    client: TestClient, workspace: dict, pdf_bytes: bytes, storage_dir
) -> None:
    response = _upload(client, workspace["id"], "../../..\\windows\\evil.pdf", pdf_bytes)
    assert response.status_code == 201
    assert response.json()["original_filename"] == "evil.pdf"
    stored = list((storage_dir / "documents" / workspace["id"]).iterdir())
    assert len(stored) == 1 and stored[0].name != "evil.pdf"


def test_list_search_and_filter(client: TestClient, workspace: dict, pdf_bytes: bytes) -> None:
    _upload(client, workspace["id"], "Sale Deed.pdf", pdf_bytes)
    _upload(client, workspace["id"], "किराया अनुबंध.pdf", pdf_bytes)
    other = client.post("/api/v1/workspaces", json={"name": "Other"}).json()
    _upload(client, other["id"], "Sale Agreement.pdf", pdf_bytes)

    assert len(client.get("/api/v1/documents").json()) == 3
    scoped = client.get("/api/v1/documents", params={"workspace_id": workspace["id"]}).json()
    assert len(scoped) == 2
    found = client.get("/api/v1/documents", params={"search": "sale"}).json()
    assert {d["original_filename"] for d in found} == {"Sale Deed.pdf", "Sale Agreement.pdf"}
    hindi = client.get("/api/v1/documents", params={"search": "किराया"}).json()
    assert [d["original_filename"] for d in hindi] == ["किराया अनुबंध.pdf"]
    # LIKE wildcards in user input are treated literally.
    assert client.get("/api/v1/documents", params={"search": "%"}).json() == []
    assert len(client.get("/api/v1/documents", params={"status": "uploaded"}).json()) == 3
    assert client.get("/api/v1/documents", params={"status": "completed"}).json() == []
    # The Phase 1 status "ready" was replaced by "completed" and is now rejected.
    assert client.get("/api/v1/documents", params={"status": "ready"}).status_code == 422


def test_delete_document_removes_file(
    client: TestClient, workspace: dict, pdf_bytes: bytes, storage_dir
) -> None:
    doc = _upload(client, workspace["id"], "a.pdf", pdf_bytes).json()
    assert client.delete(f"/api/v1/documents/{doc['id']}").status_code == 204
    assert client.get(f"/api/v1/documents/{doc['id']}").status_code == 404
    assert not any((storage_dir / "documents" / workspace["id"]).iterdir())
    assert client.delete(f"/api/v1/documents/{doc['id']}").status_code == 404
