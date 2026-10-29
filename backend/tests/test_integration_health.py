import os
import pytest
from fastapi.testclient import TestClient
from app.main import create_app


@pytest.mark.integration
@pytest.mark.skipif(os.getenv("RUN_INTEGRATION") != "1", reason="Set RUN_INTEGRATION=1 against migrated PostgreSQL and Redis")
def test_real_database_vector_migration_and_redis():
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/health/ready")
    assert response.status_code == 200, response.json()
    assert response.json()["status"] == "ready"
    assert all(check["status"] == "healthy" for check in response.json()["checks"].values())
