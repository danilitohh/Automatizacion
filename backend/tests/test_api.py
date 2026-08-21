"""Pruebas del contrato HTTP inicial de FastAPI."""

from fastapi.testclient import TestClient

from backend.app.config.settings import Settings
from backend.app.main import create_app


def test_health_and_dashboard_endpoints(tmp_path):
    """La aplicación recién instalada responde salud y dashboard vacío."""

    settings = Settings(
        database_path=tmp_path / "api-test.db",
        storage_dir=tmp_path / "storage",
    )
    application = create_app(settings)

    with TestClient(application) as client:
        health_response = client.get("/api/health")
        dashboard_response = client.get("/api/dashboard/summary")

    assert health_response.status_code == 200
    assert health_response.json()["status"] == "ok"
    assert dashboard_response.status_code == 200
    assert dashboard_response.json()["total_today"] == 0
