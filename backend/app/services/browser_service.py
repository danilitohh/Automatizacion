"""Apertura temporal de navegadores, sin perfiles personales ni corporativos."""

from typing import Any


async def launch_browser(playwright: Any, name: str, *, headless: bool) -> Any:
    """Abre Google Chrome en un contexto temporal sin cargar perfiles guardados.

    Los nombres históricos se aceptan para migrar configuraciones existentes,
    pero todos terminan usando el canal instalado de Google Chrome.
    """

    if name not in {"chrome", "chrome_incognito", "chromium", "firefox", "webkit", "brave"}:
        raise ValueError(f"Navegador no admitido: {name}")
    return await playwright.chromium.launch(channel="chrome", headless=headless)
