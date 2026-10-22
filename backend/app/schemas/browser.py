"""Normalización del navegador permitido por las automatizaciones."""

from typing import Any, Literal


BrowserName = Literal["chrome_incognito"]
_LEGACY_BROWSER_NAMES = frozenset(
    {"chrome", "chrome_incognito", "chromium", "firefox", "webkit", "brave"}
)


def normalize_browser(value: Any) -> str:
    """Conserva compatibilidad con configuraciones antiguas y usa Chrome temporal."""

    if isinstance(value, str) and value.strip().casefold() in _LEGACY_BROWSER_NAMES:
        return "chrome_incognito"
    raise ValueError("Solo se admite Google Chrome - Incógnito para las automatizaciones.")
