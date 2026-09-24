import asyncio
import httpx
import sqlite3
from types import SimpleNamespace
import pytest
from backend.app.api.routes import _fallback_us_test_lead, _reserve_lead_for_case
from backend.app.services.test_lead_service import TestLeadService
from backend.app.services.ai_service import AIService


@pytest.mark.parametrize('country', TestLeadService.COUNTRY_REGIONS)
def test_generated_phone_is_valid_and_unique(country, tmp_path):
    service = TestLeadService(tmp_path / 'qa.db', allow_synthetic_real_phones=True)
    leads = service.reserve_many([country] * 3)
    assert len({lead['phone'] for lead in leads}) == 3
    assert all(service._is_valid_generated_phone(lead['phone'], country) for lead in leads)


def test_usa_generator_expands_beyond_legacy_single_prefix(tmp_path):
    """USA no se agota cuando ya fueron usados los 100 números antiguos."""

    service = TestLeadService(tmp_path / "usa.db", allow_synthetic_real_phones=True)
    used = {f"20255501{suffix:02d}" for suffix in range(100)}

    phone = service._generated_phone("usa", "USA", 4, used)

    assert phone not in used
    assert any(
        phone.startswith(prefix)
        for prefix in service.SYNTHETIC_GENERATION_PREFIX_POOLS["usa"]
    )
    assert service._is_valid_generated_phone(phone, "usa")


def test_usa_fallback_reserves_valid_unique_numbers(tmp_path):
    """El respaldo local recorre códigos de área sin exceder su índice."""

    database_path = tmp_path / "usa-fallback.db"
    service = TestLeadService(database_path, allow_synthetic_real_phones=True)
    settings = SimpleNamespace(database_path=database_path)

    first = _fallback_us_test_lead(settings, service, "USA", "usa")
    second = _fallback_us_test_lead(settings, service, "USA", "usa")

    assert first["phone"] != second["phone"]
    assert all(
        service._is_valid_generated_phone(lead["phone"], "usa")
        for lead in (first, second)
    )
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM test_leads").fetchone()[0] == 2


def test_usa_reservation_uses_local_fallback_when_ollama_fails(tmp_path, monkeypatch):
    """Weekly Forms puede reservar el lead de USA sin depender de Ollama."""

    async def unavailable(*args, **kwargs):
        raise RuntimeError("Ollama no disponible")

    monkeypatch.setattr(AIService, "generate", unavailable)
    database_path = tmp_path / "usa-weekly-forms.db"
    service = TestLeadService(database_path, allow_synthetic_real_phones=True)
    settings = SimpleNamespace(database_path=database_path, ollama_local_model="qa")

    lead = asyncio.run(
        _reserve_lead_for_case(
            settings, service, "USA", require_authorized_phone=False
        )
    )

    assert service._is_valid_generated_phone(lead["phone"], "usa")
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM test_leads").fetchone()[0] == 1


def test_preview_phone_reads_authorized_bank_without_consuming_it(tmp_path):
    """La inspección usa un número autorizado sin insertar una reserva."""

    service = TestLeadService(
        tmp_path / "preview.db",
        authorized_phones={"USA": ["+12125550100"]},
        allow_synthetic_real_phones=True,
    )

    phone = service.preview_phone("USA", 1, set())

    assert phone == "2125550100"
    with sqlite3.connect(service.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM test_leads").fetchone()[0] == 0


@pytest.mark.parametrize('payload', [
    {'error': 'model unavailable'}, {'error': {'message': 'model unavailable'}},
    'model unavailable',
])
def test_ollama_error_formats(payload):
    response = httpx.Response(404, json=payload)
    assert 'model unavailable' in AIService._provider_error_message(response)
