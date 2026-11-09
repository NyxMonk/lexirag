from fastapi.testclient import TestClient


def test_health_reports_database_and_pgvector(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"]["status"] == "ok"
    assert body["database"]["pgvector"] is True


def test_system_info_never_exposes_secrets(client: TestClient) -> None:
    response = client.get("/api/v1/system/info")
    assert response.status_code == 200
    body = response.json()
    assert {lang["code"] for lang in body["supported_languages"]} == {"en", "hi", "bn", "mr", "pa", "fr"}
    assert isinstance(body["retrieval_engine_available"], bool)  # true once BGE-M3 is downloaded
    assert body["answering_available"] is False  # no LLM provider in tests
    assert body["model_provider"]["provider"] == "none"
    assert body["model_provider"]["configured"] is False
    assert "api_key" not in response.text.lower()


def test_unknown_route_uses_error_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_cors_allows_frontend_origin(client: TestClient) -> None:
    response = client.options(
        "/api/v1/workspaces",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_request_id_header_is_sanitised(client: TestClient) -> None:
    good = client.get("/api/v1/health", headers={"X-Request-ID": "abc-123"})
    assert good.headers["x-request-id"] == "abc-123"
    bad = client.get("/api/v1/health", headers={"X-Request-ID": "x" * 200})
    assert bad.headers["x-request-id"] != "x" * 200 and len(bad.headers["x-request-id"]) == 12
