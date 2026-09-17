from pathlib import Path

from app.api.routes import _ollama_phone_prompt
from app.services.test_lead_service import TestLeadService


def test_colombia_synthetic_phone_generation_survives_high_sequence(tmp_path: Path):
    """La serie colombiana sigue generando teléfonos válidos con historiales grandes."""

    service = TestLeadService(tmp_path / "colombia.db", allow_synthetic_real_phones=True)

    # Las filas 16-18 se ejecutan después de muchos leads; este valor reproduce
    # una secuencia alta sin depender de la base de datos local del usuario.
    phone = service._generated_phone("colombia", "Colombia", 1348, set())

    assert phone.startswith("321")
    assert len(phone) == 10
    assert service._is_valid_generated_phone(phone, "colombia")


def test_colombia_synthetic_reservations_remain_unique(tmp_path: Path):
    """Las reservas consecutivas no repiten la serie móvil colombiana."""

    service = TestLeadService(tmp_path / "colombia-unique.db", allow_synthetic_real_phones=True)
    leads = service.reserve_many(["Colombia"] * 3)

    phones = [lead["phone"] for lead in leads]
    assert len(set(phones)) == len(phones)
    assert all(phone.startswith("321") for phone in phones)


def test_colombia_ollama_prompt_uses_valid_generation_series(tmp_path: Path):
    """La sugerencia de IA pide la misma serie móvil que valida el generador."""

    service = TestLeadService(tmp_path / "colombia-prompt.db", allow_synthetic_real_phones=True)
    prompt = _ollama_phone_prompt(service, "Colombia", set(), 1)

    assert "comenzar con 321" in prompt
