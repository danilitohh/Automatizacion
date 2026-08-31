import asyncio
from unittest.mock import AsyncMock, Mock

from backend.app.automations.utel_inconcert.runner import UtelInconcertRunner
from backend.app.config.settings import Settings
from backend.app.schemas.bot import UtelLead, UtelQaConfig


def _config(form_type: str) -> UtelQaConfig:
    return UtelQaConfig(
        country="Mexico",
        utel_url="https://utel.edu.mx/doctorado-en-linea",
        modality="En linea",
        level="Doctorado",
        form_type=form_type,
        workflow_mode="form_validation",
        lead=UtelLead(),
    )


def test_footer_and_lateral_stay_on_the_excel_url():
    for form_type in ("footer", "lateral"):
        runner = UtelInconcertRunner(Settings())
        runner._click_first_program_card = AsyncMock()
        page = AsyncMock()

        asyncio.run(runner._navigate_form_validation(page, _config(form_type)))

        runner._click_first_program_card.assert_not_awaited()
        page.wait_for_load_state.assert_not_awaited()


def test_tarjeta_opens_a_program_before_looking_for_the_form():
    runner = UtelInconcertRunner(Settings())
    runner._click_first_program_card = AsyncMock()
    runner._capture_selected_program = AsyncMock()
    page = AsyncMock()

    asyncio.run(runner._navigate_form_validation(page, _config("tarjeta")))

    runner._click_first_program_card.assert_awaited_once_with(page)
    page.wait_for_load_state.assert_awaited_once_with("domcontentloaded")
    runner._capture_selected_program.assert_awaited_once_with(page)


def test_footer_scrolls_before_returning_form(monkeypatch):
    runner = UtelInconcertRunner(Settings())
    form = AsyncMock()
    page = Mock()
    page.locator.return_value.first = form
    page.locator.return_value.inner_text = AsyncMock(return_value="Formulario UTEL")
    monkeypatch.setattr("backend.app.automations.utel_inconcert.runner.asyncio.sleep", AsyncMock())
    result = asyncio.run(runner._find_utel_form(page, _config("footer")))
    assert result is form
    form.scroll_into_view_if_needed.assert_awaited_once()
    assert form.wait_for.await_count == 2
