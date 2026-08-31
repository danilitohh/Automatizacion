import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from backend.app.automations.utel_inconcert.runner import UtelInconcertRunner, UtelQaError, UnconfirmedSubmission
from backend.app.config.settings import Settings
from backend.app.services.test_lead_service import TestLeadService
from backend.app.services.bot_spreadsheet_service import BotSpreadsheetService


def test_global_country_requires_explicit_philippines_context():
    service = BotSpreadsheetService()
    assert service.effective_country("Global", "Filipinas Bachelor", "https://utel.edu.mx") == "Filipinas"
    assert service.effective_country("Global", "Bachelor", "https://utel.edu.mx/philippines/") == "Filipinas"
    assert service.effective_country("Global", "Bachelor", "https://utel.edu.mx") == "Global"
    assert "singapur" in service.default_inconcert_url("Filipinas")


@pytest.mark.parametrize("message,error", [
    ("Successfully submitted\nYour information has been received", None),
    ("Error al enviar. Contacta a soporte", UtelQaError),
    ("Mensaje desconocido", UnconfirmedSubmission),
])
def test_toast_with_saved_spanish_pattern(message, error):
    runner = UtelInconcertRunner(Settings())
    runner._last_submit_success_pattern = "envio correcto"
    submit = AsyncMock()
    submit.is_enabled.return_value = True
    form = Mock()
    form.locator.return_value.first = submit
    toast = AsyncMock()
    toast.inner_text.return_value = message
    page = Mock(wait_for_function=AsyncMock())
    page.locator.return_value = toast
    if error:
        with pytest.raises(error):
            asyncio.run(runner._submit_utel_form(page, form))
    else:
        asyncio.run(runner._submit_utel_form(page, form))
    submit.evaluate.assert_awaited_once()


def test_blocked_heading_is_not_a_program():
    runner = UtelInconcertRunner(Settings())
    page = Mock()
    page.locator.return_value.inner_text = AsyncMock(return_value="Sorry, you have been blocked")
    with pytest.raises(UtelQaError) as caught:
        asyncio.run(runner._capture_selected_program(page))
    assert caught.value.stage == "utel_access"
    assert runner.selected_program_name == ""


def test_geographic_fields_only():
    runner = UtelInconcertRunner(Settings())
    fields = [AsyncMock() for _ in range(3)]
    for field, metadata in zip(fields, ["educationLevelInput Area de interes", "province Selecciona una provincia", "city Ciudad:"]):
        field.is_visible.return_value = True
        field.is_enabled.return_value = True
        field.evaluate.return_value = metadata
    form = Mock()
    form.locator.return_value.count = AsyncMock(return_value=3)
    form.locator.return_value.nth.side_effect = fields
    runner._select_random_select_option = AsyncMock()
    asyncio.run(runner._select_random_city(form))
    assert [call.args[0] for call in runner._select_random_select_option.await_args_list] == fields[1:]


def test_phone_prefix_survives_global_sequence_and_pool_exhaustion(tmp_path):
    service = TestLeadService(tmp_path / "leads.db")
    for _ in range(105):
        service.reserve("Mexico")
    numbers = {service.reserve("USA")["phone"] for _ in range(100)}
    assert len(numbers) == 100
    assert all(number.startswith("20255501") and len(number) == 10 for number in numbers)
    with pytest.raises(ValueError, match="agotaron"):
        service.reserve("United States")
    assert service.reserve("Dominicana")["phone"].startswith("80955501")
