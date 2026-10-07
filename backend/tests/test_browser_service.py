"""Regresiones de apertura privada para todos los módulos, sin red."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.app.services.browser_service import launch_browser


@pytest.mark.parametrize("name", ["chrome", "chrome_incognito", "chromium", "firefox", "webkit"])
def test_launch_without_saved_profile(name):
    """El valor antiguo chrome también abre sin directorio de usuario."""

    engines = {key: SimpleNamespace(launch=AsyncMock()) for key in ("chromium", "firefox", "webkit")}
    playwright = SimpleNamespace(**engines)
    asyncio.run(launch_browser(playwright, name, headless=True))
    chrome = name in {"chrome", "chrome_incognito"}
    options = {"headless": True, **({"channel": "chrome"} if chrome else {})}
    engines["chromium" if chrome else name].launch.assert_awaited_once_with(**options)


def test_app_cannot_reopen_retired_profile():
    """Cubre también ejecutores de compatibilidad y aperturas secundarias."""

    app = Path(__file__).resolve().parents[1] / "app"
    for path in app.rglob("*.py"):
        source = path.read_text(encoding="utf-8-sig")
        assert "launch_persistent_context(" not in source, str(path)
        assert "chrome-qa" not in source, str(path)
