"""Apertura temporal de navegadores, sin perfiles personales ni corporativos."""

from typing import Any


async def launch_browser(playwright: Any, name: str, *, headless: bool) -> Any:
    """Chrome antiguo y explícitamente incógnito usan el mismo contexto temporal.

    El llamador crea el contexto y conserva su ciclo de vida actual; nunca se
    carga un directorio de usuario, incluso al restaurar configuraciones antiguas.
    """

    options: dict[str, Any] = {"headless": headless}
    if name in {"chrome", "chrome_incognito", "brave"}:
        engine = playwright.chromium
        if name == "brave":
            options["executable_path"] = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
        else:
            options["channel"] = "chrome"
    elif name in {"chromium", "firefox", "webkit"}:
        engine = getattr(playwright, name)
    else:
        raise ValueError(f"Navegador no admitido: {name}")
    return await engine.launch(**options)
