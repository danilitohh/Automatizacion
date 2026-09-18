"""Navegador y pestañas reutilizables de una ejecución de Leads Deploy."""

from contextlib import suppress
from typing import Any

from ...config.settings import Settings
from ...schemas.bot import UtelQaConfig


class LeadsDeployBrowserSession:
    """Conserva cookies, almacenamiento y hasta una pestaña por función."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.playwright: Any = None
        self.browser: Any = None
        self.context: Any = None
        self.pages: dict[str, Any] = {}
        self.window_maximized = False

    async def start(self, config: UtelQaConfig) -> None:
        """Abre el navegador una sola vez, incluso durante preflight y reintentos."""

        if self.context is not None:
            return
        try:
            from playwright.async_api import async_playwright
        except ImportError as error:
            raise RuntimeError(
                "Playwright no está instalado. Instala backend/requirements.txt "
                "y ejecuta python -m playwright install chromium."
            ) from error

        self.playwright = await async_playwright().start()
        try:
            headless = False if config.keep_browser_open else config.headless
            if config.browser in {"chrome", "brave"}:
                profile = self.settings.storage_dir / "browser_profiles" / "chrome-qa"
                profile.mkdir(parents=True, exist_ok=True)
                options = {"headless": headless, "viewport": {"width": 1440, "height": 900}}
                if config.browser == "brave":
                    options["executable_path"] = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
                else:
                    options["channel"] = "chrome"
                self.context = await self.playwright.chromium.launch_persistent_context(
                    str(profile), **options
                )
            else:
                self.browser = await getattr(self.playwright, config.browser).launch(headless=headless)
                self.context = await self.browser.new_context(viewport={"width": 1440, "height": 900})
        except BaseException:
            # También libera el driver si se cancela o falla la apertura.
            await self.close()
            raise

    async def page(self, role: str) -> Any:
        """Reutiliza UTEL/InConcert/Balanceador sin acumular pestañas por fila."""

        page = self.pages.get(role)
        if page is None or page.is_closed():
            # Chrome persistente puede traer una pestaña vacía inicial.
            page = next(
                (item for item in self.context.pages
                 if item not in self.pages.values() and item.url == "about:blank"),
                None,
            )
            if page is None:
                page = await self.context.new_page()
            self.pages[role] = page
        return page

    async def discard_detail_tabs(self) -> None:
        """Retira popups de evidencias anteriores al empezar la siguiente fila."""

        for page in list(self.context.pages):
            if page not in self.pages.values() and page.url != "about:blank":
                with suppress(Exception):
                    # Solo se retiran popups del bot, no pestañas del usuario.
                    if await page.opener() in self.pages.values():
                        await page.close()

    async def close(self) -> None:
        """Libera cada recurso aunque otro ya haya sido cerrado por el usuario."""

        context, browser, playwright = self.context, self.browser, self.playwright
        self.context = self.browser = self.playwright = None
        self.pages.clear()
        for resource, method in ((context, "close"), (browser, "close"), (playwright, "stop")):
            if resource is not None:
                with suppress(Exception):
                    await getattr(resource, method)()
