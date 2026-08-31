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
