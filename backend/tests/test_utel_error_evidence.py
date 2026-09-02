import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from backend.app.automations.utel_inconcert.runner import UtelInconcertRunner, UtelQaError
from backend.app.config.settings import Settings


def test_failure_captures_evidence_while_page_is_open():
    runner = UtelInconcertRunner(Settings())
    page = Mock(url="https://example.test/form")
    runner._safe_screenshot = AsyncMock(return_value="error.png")
    action = AsyncMock(side_effect=RuntimeError("campo incompleto"))
    with pytest.raises(UtelQaError) as caught:
        asyncio.run(runner._run_stage(4, "utel_fill", "Lleno", page, action))
    assert caught.value.stage == "utel_fill"
    assert caught.value.screenshot == "error.png"
    assert caught.value.url == page.url
    runner._safe_screenshot.assert_awaited_once_with(page, "error_utel_fill")


def test_business_failure_keeps_selector_and_evidence():
    runner = UtelInconcertRunner(Settings())
    runner._safe_screenshot = AsyncMock(return_value="program.png")
    error = UtelQaError("utel_fill", "No hay programas", "#program")
    with pytest.raises(UtelQaError) as caught:
        asyncio.run(runner._run_stage(4, "utel_fill", "Lleno", Mock(url="https://example.test"), AsyncMock(side_effect=error)))
    assert caught.value is error
    assert error.selector == "#program"
    assert error.screenshot == "program.png"


def test_submit_without_confirmation_is_never_success():
    runner = UtelInconcertRunner(Settings())
    submit = AsyncMock()
    submit.is_enabled.return_value = True
    form = Mock()
    form.locator.return_value.first = submit
    page = Mock()
    page.locator.return_value.wait_for = AsyncMock(side_effect=TimeoutError("no toast"))
    with pytest.raises(UtelQaError, match="Envio no confirmado"):
        asyncio.run(runner._submit_utel_form(page, form))
    submit.evaluate.assert_awaited_once()
    submit.scroll_into_view_if_needed.assert_not_awaited()


def test_deferred_submission_without_visual_confirmation_waits_for_crm_without_resending(tmp_path):
    """Un lote conserva un envío incierto para verificarlo en CRM una sola vez."""

    runner = UtelInconcertRunner(Settings(storage_dir=tmp_path))
    page = Mock(url="https://utel.test")
    context = Mock(new_page=AsyncMock(return_value=page), close=AsyncMock())
    browser = Mock(new_context=AsyncMock(return_value=context), close=AsyncMock())
    playwright = Mock()
    playwright.chromium.launch = AsyncMock(return_value=browser)

    from contextlib import asynccontextmanager
    from backend.app.automations.utel_inconcert.runner import UnconfirmedSubmission
    from backend.app.schemas.bot import UtelLead, UtelQaConfig

    @asynccontextmanager
    async def runtime(*args):
        yield playwright

    runner._playwright = runtime
    runner._close_open_session = AsyncMock()
    runner._safe_screenshot = AsyncMock(return_value=None)
    for name in ("_open_utel", "_navigate_utel", "_find_utel_form", "_fill_utel_form"):
        setattr(runner, name, AsyncMock(return_value=Mock()))
    runner._submit_utel_form = AsyncMock(side_effect=UnconfirmedSubmission("utel_submit", "Sin confirmación visual"))
    config = UtelQaConfig(
        country="Panama", utel_url="https://utel.test", inconcert_url="https://crm.test",
        modality="En linea", level="Licenciatura", form_type="footer", dry_run=False,
        defer_crm_verification=True, lead=UtelLead(),
    )

    result = asyncio.run(runner.run(config))

    assert result["status"] == "PASS"
    assert result["utel_submission"] == "pending"
    assert "sin reenviar" in result["utel_submission_message"]
    runner._submit_utel_form.assert_awaited_once()


def test_screenshot_falls_back_to_viewport_and_preserves_prior_runs(tmp_path):
    runner = UtelInconcertRunner(Settings(storage_dir=tmp_path / "storage"))
    first_directory = runner._evidence_directory("same row")
    second_directory = runner._evidence_directory("same row")
    assert first_directory != second_directory
    runner.evidence_directory = second_directory
    page = AsyncMock()
    page.screenshot.side_effect = [TimeoutError("full page"), None]
    path = asyncio.run(runner._safe_screenshot(page, "error"))
    assert path is not None
    assert page.screenshot.await_args_list[0].kwargs["full_page"] is True
    assert page.screenshot.await_args_list[1].kwargs["full_page"] is False
    assert runner.screenshots == [path]


def test_screenshot_retries_without_disabling_animations(tmp_path):
    runner = UtelInconcertRunner(Settings(storage_dir=tmp_path / "storage"))
    runner.evidence_directory = runner._evidence_directory("slow page")
    page = AsyncMock()
    page.screenshot.side_effect = [TimeoutError("full"), TimeoutError("viewport"), None]

    path = asyncio.run(runner._safe_screenshot(page, "slow"))

    assert path is not None
    assert page.screenshot.await_count == 3
    assert "animations" not in page.screenshot.await_args_list[2].kwargs
