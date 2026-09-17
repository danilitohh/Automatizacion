from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlparse

from playwright.async_api import async_playwright


class BalancerCatalogError(RuntimeError):
    """Safe-to-display error raised while reading the Balanceador catalog."""


def _normalize(value: str) -> str:
    plain = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", plain.casefold()).split())


def _is_manual_challenge(url: str, title: str, body: str) -> bool:
    searchable = f"{url} {title} {body}".casefold()
    return any(
        marker in searchable
        for marker in (
            "__cf_chl",
            "cdn-cgi/challenge",
            "just a moment",
            "verify you are human",
            "checking your browser",
        )
    )


def program_lookup_details(program: str) -> tuple[str, str | None]:
    """Return the base product name and degree used to disambiguate catalog rows."""

    value = " ".join(str(program).strip().split())
    match = re.match(r"^(licenciatura|maestr[ií]a|doctorado)(?:\s+en)?\s+(.+)$", value, re.I)
    if not match:
        return value, None
    degree = _normalize(match.group(1))
    level = {"licenciatura": "licenciatura", "maestria": "maestria", "doctorado": "doctorado"}[degree]
    return match.group(2).strip(), level


def _row_level_matches(value: str, expected: str | None) -> bool:
    if expected is None:
        return True
    level = _normalize(value)
    aliases = {
        "licenciatura": {"licenciatura", "licenciaturas"},
        "maestria": {"maestria", "master", "masters", "maestria ejecutiva"},
        "doctorado": {"doctorado", "doctorate", "doctoral"},
    }
    return level in aliases[expected]


def select_catalog_code(rows: list[list[str]], program: str) -> str:
    """Select the exact base-name/degree row from visible catalog table cells."""

    lookup_name, expected_level = program_lookup_details(program)
    matching = [
        row for row in rows
        if len(row) >= 3
        and _normalize(row[1]) == _normalize(lookup_name)
        and _row_level_matches(row[2], expected_level)
        and row[0].strip()
    ]
    codes = list(dict.fromkeys(row[0].strip() for row in matching))
    if not codes:
        level_note = f" con nivel {expected_level}" if expected_level else ""
        raise BalancerCatalogError(
            f"No se encontró el programa {lookup_name!r}{level_note} en el catálogo del Balanceador."
        )
    if len(codes) > 1:
        raise BalancerCatalogError(
            f"La búsqueda de {lookup_name!r} devolvió varios códigos para el nivel del producto."
        )
    return codes[0]


class BalancerProgramCatalog:
    """Read SIU keys from the Balanceador program-of-interest catalog."""

    def __init__(self, leads_url: str, username: str = "", password: str = "") -> None:
        parsed = urlparse(leads_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("La URL del Balanceador no es válida.")
        self.origin = f"{parsed.scheme}://{parsed.netloc}"
        self.username = username.strip()
        self.password = password
        self.playwright = None
        self.browser = None
        self.page = None

    async def start(self) -> None:
        if self.page is not None:
            return
        self.playwright = await async_playwright().start()
        try:
            self.browser = await self.playwright.chromium.launch(headless=True)
            context = await self.browser.new_context()
            self.page = await context.new_page()
            await self._open_catalog()
        except BalancerCatalogError:
            await self.close()
            raise
        except Exception as error:
            await self.close()
            raise BalancerCatalogError(
                "No se pudo abrir o autenticar el catálogo del Balanceador."
            ) from error

    async def close(self) -> None:
        if self.browser is not None:
            await self.browser.close()
            self.browser = None
        if self.playwright is not None:
            await self.playwright.stop()
            self.playwright = None
        self.page = None

    async def get_siu_key(self, program: str) -> str:
        """Search by base name only, then use degree level to choose its SIU key."""

        await self.start()
        lookup_name, _ = program_lookup_details(program)
        search = self.page.locator("input[type='search']:visible").first
        await search.wait_for(state="visible", timeout=30000)
        await search.fill(lookup_name)
        # This catalog's DataTables search applies on Enter.
        await search.press("Enter")
        await self.page.locator("table tbody tr").first.wait_for(state="visible", timeout=30000)
        rows = await self.page.locator("table tbody tr:visible").evaluate_all(
            "rows => rows.map(row => Array.from(row.cells).map(cell => cell.innerText.trim()))"
        )
        return select_catalog_code(rows, program)

    async def _open_catalog(self) -> None:
        catalog_url = f"{self.origin}/catalog/program-of-interest"
        await self.page.goto(catalog_url, wait_until="domcontentloaded", timeout=60000)
        await self._stop_for_challenge()

        password = self.page.locator("input[type='password']:visible").first
        login_path = "/login" in self.page.url
        if login_path or await password.count():
            if not self.username or not self.password:
                raise BalancerCatalogError(
                    "El Balanceador requiere inicio de sesión y no hay credenciales configuradas."
                )
            await self.page.goto(
                f"{self.origin}/login/?next=/catalog/program-of-interest",
                wait_until="domcontentloaded",
                timeout=60000,
            )
            await self._stop_for_challenge()
            username_input = self.page.locator(
                "input[name='email']:visible, input[name='username']:visible, "
                "input[name='login']:visible, input[type='email']:visible, "
                "input[autocomplete='username']:visible, input[type='text']:visible"
            ).first
            password_input = self.page.locator("input[type='password']:visible").first
            await username_input.fill(self.username)
            await password_input.fill(self.password)
            await self.page.locator(
                "button[type='submit']:visible, input[type='submit']:visible, "
                "button:has-text('Ingresar'):visible, button:has-text('Iniciar'):visible, "
                "button:has-text('Login'):visible"
            ).first.click()
            try:
                await self.page.wait_for_function(
                    "() => !location.pathname.startsWith('/login')",
                    timeout=30000,
                )
            except Exception as error:
                raise BalancerCatalogError(
                    "No se pudo iniciar sesión en el Balanceador para consultar el catálogo."
                ) from error
            await self._stop_for_challenge()
            await self.page.goto(catalog_url, wait_until="domcontentloaded", timeout=60000)

        await self.page.locator("input[type='search']:visible").first.wait_for(
            state="visible", timeout=30000
        )

    async def _stop_for_challenge(self) -> None:
        title = await self.page.title()
        body = await self.page.locator("body").inner_text()
        if _is_manual_challenge(self.page.url, title, body):
            raise BalancerCatalogError(
                "El Balanceador solicita una verificación manual antes de abrir el catálogo."
            )
