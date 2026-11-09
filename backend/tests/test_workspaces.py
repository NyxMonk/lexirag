import uuid

from fastapi.testclient import TestClient


def test_create_and_list_workspaces(client: TestClient) -> None:
    created = client.post(
        "/api/v1/workspaces", json={"name": "  Tenancy disputes  ", "description": "Pune matters"}
    )
    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "Tenancy disputes"
    assert body["description"] == "Pune matters"
    assert body["document_count"] == 0

    listing = client.get("/api/v1/workspaces")
    assert listing.status_code == 200
    assert [w["id"] for w in listing.json()] == [body["id"]]


def test_get_workspace_counts_documents(client: TestClient, workspace: dict, pdf_bytes: bytes) -> None:
    client.post(
        "/api/v1/documents/upload",
        data={"workspace_id": workspace["id"]},
        files={"file": ("a.pdf", pdf_bytes, "application/pdf")},
    )
    response = client.get(f"/api/v1/workspaces/{workspace['id']}")
    assert response.status_code == 200
    assert response.json()["document_count"] == 1


def test_create_workspace_rejects_blank_name(client: TestClient) -> None:
    response = client.post("/api/v1/workspaces", json={"name": "   "})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_unicode_workspace_names(client: TestClient) -> None:
    for name in ["किरायेदारी विवाद", "জমি মামলা", "ਜ਼ਮੀਨ ਦਾ ਕੇਸ"]:
        response = client.post("/api/v1/workspaces", json={"name": name})
        assert response.status_code == 201
        assert response.json()["name"] == name


def test_missing_workspace_returns_404(client: TestClient) -> None:
    response = client.get(f"/api/v1/workspaces/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_delete_workspace_removes_documents_and_files(
    client: TestClient, workspace: dict, pdf_bytes: bytes, storage_dir
) -> None:
    uploaded = client.post(
        "/api/v1/documents/upload",
        data={"workspace_id": workspace["id"]},
        files={"file": ("a.pdf", pdf_bytes, "application/pdf")},
    ).json()
    workspace_dir = storage_dir / "documents" / workspace["id"]
    assert any(workspace_dir.iterdir())

    assert client.delete(f"/api/v1/workspaces/{workspace['id']}").status_code == 204
    assert client.get(f"/api/v1/workspaces/{workspace['id']}").status_code == 404
    assert client.get(f"/api/v1/documents/{uploaded['id']}").status_code == 404
    assert not workspace_dir.exists()
