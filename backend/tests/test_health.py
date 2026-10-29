from fastapi.testclient import TestClient
from app.main import create_app
from app.api.health import Check


def test_liveness_needs_no_infrastructure():
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "alive"
    assert response.headers["x-request-id"]
    assert response.headers["cache-control"] == "no-store"


def test_readiness_does_not_claim_success_on_database_failure(monkeypatch):
    bad = Check(status="unavailable", detail="Unavailable")
    good = Check(status="healthy", detail="Connected")
    monkeypatch.setattr("app.api.health.probe_database", lambda: (bad, bad, bad))
    monkeypatch.setattr("app.api.health.probe_redis", lambda: good)
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"


def test_readiness_requires_every_dependency(monkeypatch):
    good = Check(status="healthy", detail="Connected")
    monkeypatch.setattr("app.api.health.probe_database", lambda: (good, good, good))
    monkeypatch.setattr("app.api.health.probe_redis", lambda: good)
    with TestClient(create_app()) as client:
        assert client.get("/api/v1/health/ready").json()["status"] == "ready"


def test_not_found_has_consistent_error_shape():
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/missing")
    assert response.status_code == 404
    assert response.json()["error"]["request_id"]


def test_cors_rejects_unknown_origin():
    with TestClient(create_app()) as client:
        response = client.options("/api/v1/health/live", headers={"origin": "https://untrusted.example", "access-control-request-method": "GET"})
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
