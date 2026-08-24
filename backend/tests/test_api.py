"""Pruebas del contrato HTTP inicial de FastAPI."""

from fastapi.testclient import TestClient
from pydantic import SecretStr

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


def test_pdp_validation_rejects_wrong_file_extensions(tmp_path):
    """El endpoint PDP detiene archivos equivocados antes de abrir Playwright."""

    settings = Settings(database_path=tmp_path / "api-test.db", storage_dir=tmp_path / "storage")
    application = create_app(settings)

    with TestClient(application) as client:
        response = client.post(
            "/api/pdp/validate",
            files={
                "excel_file": ("programas.csv", b"Programa,URL", "text/csv"),
                "docx_file": ("contenido.docx", b"archivo", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            },
        )

    assert response.status_code == 400
    assert ".xlsx" in response.json()["detail"]


def test_ai_provider_status_never_returns_keys(tmp_path):
    """El endpoint de estado solo expone configuración y modelo."""

    settings = Settings(
        database_path=tmp_path / "api-test.db",
        storage_dir=tmp_path / "storage",
        ollama_api_key=SecretStr("ollama-secret"),
        groq_api_key=SecretStr("groq-secret"),
        gemini_api_key=SecretStr("gemini-secret"),
    )
    application = create_app(settings)

    with TestClient(application) as client:
        response = client.get("/api/ai/providers")

    assert response.status_code == 200
    payload = response.json()
    assert all(provider["configured"] for provider in payload["providers"])
    assert "ollama-secret" not in response.text
    assert "groq-secret" not in response.text
    assert "gemini-secret" not in response.text


def test_semantic_pdp_rejects_unsupported_source_before_browser(tmp_path):
    """El modo genÃ©rico valida formato y URL antes de iniciar Playwright."""

    settings = Settings(database_path=tmp_path / "api-test.db", storage_dir=tmp_path / "storage")
    application = create_app(settings)

    with TestClient(application) as client:
        response = client.post(
            "/api/pdp/semantic-validate",
            data={"url": "https://example.com", "use_ai": "false"},
            files={"source_file": ("fuente.exe", b"contenido", "application/octet-stream")},
        )

    assert response.status_code == 400
    assert "Formato no soportado" in response.json()["detail"]
