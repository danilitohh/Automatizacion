"""Regresiones de sesión única y navegación sin recargas redundantes."""

import asyncio
import io
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from backend.app.automations.leads_deploy.runner import LeadsDeployRunner
from backend.app.config.settings import Settings
from backend.app.main import create_app
from backend.app.modules.bot_leads_deploy.browser_session import LeadsDeployBrowserSession
from backend.app.schemas.bot import UtelLead, UtelQaConfig


def _config(**updates):
    """Configuración sin envíos reales para todas las pruebas de navegador."""

    values = dict(country="Mexico", utel_url="https://landing.test/one", modality="En linea",
                  level="Licenciatura", lead=UtelLead(), fill_only=True, headless=True,
                  browser="chromium", workflow_mode="form_validation")
    return UtelQaConfig(**(values | updates))


@pytest.mark.parametrize("browser_name", ["chromium", "chrome"])
def test_session_launches_once_and_reuses_pages(tmp_path, monkeypatch, browser_name):
    """Valida ambos modos de apertura y que se conservan tres pestañas como máximo."""

    async def scenario():
        pages = []

        async def new_page():
            page = Mock(url="about:blank", is_closed=Mock(return_value=False), close=AsyncMock())
            pages.append(page)
            return page

        context = SimpleNamespace(pages=pages, new_page=AsyncMock(side_effect=new_page), close=AsyncMock())
        browser = SimpleNamespace(new_context=AsyncMock(return_value=context), close=AsyncMock())
        engine = SimpleNamespace(launch=AsyncMock(return_value=browser),
                                 launch_persistent_context=AsyncMock(return_value=context))
        driver = SimpleNamespace(chromium=engine, stop=AsyncMock())
        factory = Mock(return_value=SimpleNamespace(start=AsyncMock(return_value=driver)))
        monkeypatch.setattr("playwright.async_api.async_playwright", factory)
        session = LeadsDeployBrowserSession(Settings(storage_dir=tmp_path))
        for _ in range(3):
            await session.start(_config(browser=browser_name))
            for role in ("utel", "inconcert", "balancer"):
                page = await session.page(role)
                page.url = f"https://{role}.test/"
                assert await session.page(role) is page
        factory.assert_called_once()
        assert engine.launch.await_count + engine.launch_persistent_context.await_count == 1
        assert len(pages) == 3
        context.close.assert_not_awaited()
        await session.close()
        context.close.assert_awaited_once()
        driver.stop.assert_awaited_once()

    asyncio.run(scenario())


@pytest.mark.parametrize("cancelled,keep_open", [(False, False), (False, True), (True, True)])
def test_batch_cleanup_happens_only_at_end(tmp_path, cancelled, keep_open):
    """La cancelación siempre libera el navegador; revisión manual solo al terminar."""

    async def scenario():
        runner = LeadsDeployRunner(Settings(storage_dir=tmp_path))
        context = SimpleNamespace(close=AsyncMock(), pages=[])
        driver = SimpleNamespace(stop=AsyncMock())
        try:
            async with runner.batch_browser(_config(keep_browser_open=keep_open)):
                session = runner._batch_browser
                session.context, session.playwright = context, driver
                async with runner._browser_context(_config()):
                    pass
                async with runner._browser_context(_config()):
                    context.close.assert_not_awaited()
                if cancelled:
                    raise asyncio.CancelledError
        except asyncio.CancelledError:
            assert cancelled
        if keep_open and not cancelled:
            context.close.assert_not_awaited()
            assert LeadsDeployRunner._open_session is session
            await runner._close_open_session()
        context.close.assert_awaited_once()
        driver.stop.assert_awaited_once()
        assert runner._batch_browser is None

    asyncio.run(scenario())


def test_ready_inconcert_skips_navigation_but_changed_country_does_not(tmp_path):
    """Evita login/listado redundantes sin confundir sesiones de dos países."""

    async def scenario():
        runner = LeadsDeployRunner(Settings(storage_dir=tmp_path))
        config = _config(inconcert_url="https://mas-utel.inconcertcc.com/login")
        page = Mock(url="https://mas-utel.inconcertcc.com/mas/contact/people", goto=AsyncMock())
        runner._is_inconcert_login = AsyncMock(return_value=False)
        runner._resolve_inconcert_search_input = AsyncMock(return_value=Mock(is_visible=AsyncMock(return_value=True)))
        await runner._open_inconcert(page, config)
        await runner._open_contacts(page)
        page.goto.assert_not_awaited()
        next_config = config.model_copy(update={"inconcert_url": "https://mas-utel-col.inconcertcc.com/login"})
        await runner._open_inconcert(page, next_config)
        page.goto.assert_awaited_once_with(next_config.inconcert_url, wait_until="domcontentloaded", timeout=60000)
        assert runner._crm_origin == "https://mas-utel-col.inconcertcc.com"

    asyncio.run(scenario())


@pytest.mark.parametrize("path,password,expected", [("/leads/", False, True), ("/login/", True, False),
                                                    ("/leads/detail/1", False, False), ("/leads/", True, False)])
def test_balancer_reuse_requires_ready_list(tmp_path, path, password, expected):
    """El listado de otro lead o un login vencido no se tratan como búsqueda lista."""

    async def scenario():
        runner = LeadsDeployRunner(Settings(storage_dir=tmp_path))
        page = Mock(url=f"https://lead-balancer.scalahed.com{path}")
        page.locator.return_value.count = AsyncMock(return_value=int(password))
        for locator in (page.get_by_label.return_value, page.get_by_role.return_value):
            locator.first.is_visible = AsyncMock(return_value=True)
        assert await runner._balancer_list_ready(page, "https://lead-balancer.scalahed.com/leads/") is expected

    asyncio.run(scenario())


@pytest.mark.parametrize("dry_run", [True, False])
def test_batch_api_awaits_each_row_with_same_session(tmp_path, monkeypatch, dry_run):
    """El endpoint real mantiene una sesión por lote y nunca solapa dos filas."""

    seen, preflight, active = [], [], 0

    async def fake_preflight(self, config):
        """Registra la sesión del chequeo CRM sin contactar servicios externos."""

        preflight.append((id(self), id(self._batch_browser)))

    async def fake_run(self, config):
        nonlocal active
        assert self._batch_browser is not None
        active += 1
        assert active == 1
        seen.append((id(self), id(self._batch_browser), config))
        await asyncio.sleep(0)
        active -= 1
        return {"status": "PASS", "dry_run": dry_run, "stages": [], "summary": "Prueba local",
                "utel_submission_attempted": not dry_run, "utel_submission": "skipped" if dry_run else "success",
                "lead_found": "skipped" if dry_run else "success",
                "lead_url": None if dry_run else "https://crm.test/lead/1"}

    monkeypatch.setattr(LeadsDeployRunner, "run", fake_run)
    monkeypatch.setattr(LeadsDeployRunner, "preflight_inconcert", fake_preflight)
    workbook = Workbook()
    workbook.active.append(["Country", "Nivel", "Activo de Test", "Location", "Url Origen Lead"])
    for level in ("Licenciatura", "Maestria", "Licenciatura"):
        workbook.active.append(["Mexico", level, "", "Lateral", "https://mas-utel.inconcertcc.com"])
    content = io.BytesIO()
    workbook.save(content)
    settings = Settings(database_path=tmp_path / "test.db", storage_dir=tmp_path / "storage", batch_delay_seconds=0,
                        inconcert_username="test", inconcert_password="test", utel_allow_synthetic_real_phones=True)
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.post("/api/bots/leads-deploy/batch-run", files={"file": ("Leads Deploy.xlsx", content.getvalue())},
                               data={"config": json.dumps({"dry_run": dry_run, "lead": {}}),
                                     "mapping": json.dumps({"country": "Country", "level": "Nivel", "form_type": "Location",
                                                            "lead_origin_url": "Url Origen Lead", "workflow_mode": "form_validation"})})
        assert response.status_code == 202, response.text
        async def finish_job():
            """Espera el worker real en su loop, sin sondeos ni sleeps arbitrarios."""

            await app.state.bot_tasks[response.json()["job_id"]]

        client.portal.call(finish_job)
        job = client.get(f"/api/bots/leads-deploy/batch/{response.json()['job_id']}").json()
        assert job["status"] == "PASS", job
        assert job["completed"] == 3
        assert not app.state.leads_deploy_browser_lock.locked()
    assert len(seen) == 3
    assert len({(runner, session) for runner, session, _ in seen}) == 1
    assert preflight == ([] if dry_run else [seen[0][:2]])


def test_real_browser_preserves_session_between_programs(tmp_path):
    """Ejecuta dos filas en Chrome real con páginas locales interceptadas, sin envíos."""

    async def scenario():
        runner = LeadsDeployRunner(Settings(storage_dir=tmp_path))
        config = _config(browser="chrome")
        rows, requests = [], []

        async def fixture(route):
            requests.append(route.request.url)
            await route.fulfill(content_type="text/html", body='<form><input name="email"></form>')

        async def find_form(page, config):
            return page.locator("form")

        async def fill(page, form, config):
            await form.locator("input").fill(config.lead.email)
            rows.append(page)

        runner._navigate_utel = AsyncMock(return_value=None)
        runner._maximize_visible_browser = AsyncMock()
        runner._find_utel_form = find_form
        runner._fill_utel_form = fill
        runner._submit_utel_form = AsyncMock(side_effect=AssertionError("No se debe enviar"))
        async with runner.batch_browser(config):
            session = runner._batch_browser
            await session.start(config)
            context = session.context
            await context.route("**/*", fixture)
            first = await runner.run(config)
            assert first["status"] == "PASS", first
            await rows[0].evaluate("localStorage.setItem('qa-session', 'preserved'); sessionStorage.setItem('qa-tab', 'preserved')")
            await context.add_cookies([{"name": "qa-session", "value": "preserved", "url": config.utel_url}])
            second = await runner.run(config.model_copy(update={"utel_url": "https://landing.test/two"}))
            assert second["status"] == "PASS", second
            assert rows[0] is rows[1]
            assert runner._batch_browser.context is context
            assert len(context.pages) == 1
            assert await rows[1].evaluate("localStorage.getItem('qa-session')") == "preserved"
            assert await rows[1].evaluate("sessionStorage.getItem('qa-tab')") == "preserved"
            assert any(cookie["name"] == "qa-session" for cookie in await context.cookies())
            assert requests == ["https://landing.test/one", "https://landing.test/two"]
            runner._submit_utel_form.assert_not_awaited()
        assert rows[0].is_closed()

    asyncio.run(scenario())
