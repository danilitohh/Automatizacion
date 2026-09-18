import httpx
import sqlite3
import pytest
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
