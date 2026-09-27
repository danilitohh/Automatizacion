import asyncio
import io
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from openpyxl import Workbook, load_workbook

from backend.app.api.routes import _run_utel_batch_job
from backend.app.config.settings import Settings
from backend.app.database.connection import get_connection
from backend.app.main import create_app
from backend.app.modules.weekly_auto.weekly_forms import (
    WeeklyFormsCaseConfig,
    WeeklyFormsRunner,
    WeeklyFormsSpreadsheetService,
)
from backend.app.modules.bot_leads_deploy.runner import UtelQaError
from backend.app.services.bot_report_service import BotReportService


def _workbook_bytes(rows):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "QA"
    sheet.append(["Country", "Nivel", "Activo de Test", "Location", "Cliente", "Lead"])
    for row in rows:
        sheet.append(row)
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def test_weekly_forms_uses_displayed_url_infers_level_and_skips_existing_lead():
    content = _workbook_bytes([
        ["USA", "", "https://universidad.utel.edu.mx/usa/licenciaturas-online", "Form Lp", "LatAm", ""],
        ["Global", "Licenciatura", "https://educacioncontinua.utel.mx/landing/educacion-continua", "Form Lp", "Mex", ""],
        ["México", "Licenciatura", "https://example.test/already", "Footer", "Mex", "https://crm.test/lead/1"],
        ["México", "Licenciatura", "https://example.test/senior", "Targeta", "Mex", ""],
    ])
    service = WeeklyFormsSpreadsheetService()
    preview = service.preview(content, "QA.xlsx")
    rows = service.rows_for_mapping(content, preview["sheets"][0]["mapping"])

    assert len(rows) == 3
    assert rows[0]["level"] == "Licenciatura"
    assert rows[1]["utel_url"].endswith("/landing/educacion-continua")
    assert rows[2]["weekly_form_type"] == "form_lp"
    assert service.BATCH_SIZE == 5
    assert service.BATCH_PAUSE_SECONDS == 60


def test_weekly_forms_preserves_cell_value_instead_of_hyperlink_target():
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Country", "Nivel", "Activo de Test", "Location", "Cliente", "Lead"])
    visible = "https://educacioncontinua.utel.mx/landing/educacion-continua"
    sheet.append(["Global", "Licenciatura", visible, "Form Lp", "Mex", ""])
    sheet.cell(2, 3).hyperlink = visible + ".html"
    output = io.BytesIO()
    workbook.save(output)
    service = WeeklyFormsSpreadsheetService()
    preview = service.preview(output.getvalue(), "QA.xlsx")
    rows = service.rows_for_mapping(output.getvalue(), preview["sheets"][0]["mapping"])
    assert rows[0]["utel_url"] == visible


def test_weekly_forms_requires_lead_output_column():
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Country", "Nivel", "Activo de Test", "Location", "Cliente"])
    sheet.append(["USA", "Licenciatura", "https://example.test/form", "Form Lp", "LatAm"])
    output = io.BytesIO()
    workbook.save(output)

    assert WeeklyFormsSpreadsheetService().preview(output.getvalue(), "QA.xlsx")["sheets"] == []


def test_weekly_forms_accepts_plural_url_leads_column():
    """La matriz QA usa URL LEADS y debe reconocer sus filas pendientes."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Country", "Nivel", "Activo de Test", "Location", "URL LEADS"])
    sheet.append(["México", "Licenciatura", "https://utel.edu.mx/programa", "Tarjeta", ""])
    sheet.append(["México", "Licenciatura", "https://utel.edu.mx/otro", "Tarjeta", "https://crm.test/lead/1"])
    output = io.BytesIO()
    workbook.save(output)

    service = WeeklyFormsSpreadsheetService()
    preview = service.preview(output.getvalue(), "leadsQA_sin_URL_LEAD.xlsx")

    assert len(preview["sheets"]) == 1
    assert preview["sheets"][0]["mapping"]["lead_url"] == "URL LEADS"
    assert preview["sheets"][0]["total_rows"] == 1
    rows = service.rows_for_mapping(output.getvalue(), preview["sheets"][0]["mapping"])
    assert [row["row_number"] for row in rows] == [2]


def test_weekly_forms_infers_country_from_url_and_global_level():
    """Country fallback handles UTEL paths and country labels in Global rows."""

    service = WeeklyFormsSpreadsheetService()
    assert service.infer_country("https://utel.edu.mx/colombia/licenciaturas") == "Colombia"
    assert service.infer_country("https://utlenlinea.com/programa") == "Peru"
    assert service.infer_country("https://utel.edu.mx/vietnam/licenciaturas") == "Vietnam"
    assert service.infer_country("https://utel.edu.mx/philippines/programa") == "Filipinas"
    assert service.effective_country(
        "Global", "Vietnam Bachelor", "https://utel.edu.mx/global/"
    ) == "Vietnam"
    assert service.effective_country(
        "Global", "Bachelor", "https://utel.edu.mx/usa"
    ) == "USA"


@pytest.mark.parametrize(
    ("message", "submission_attempted"),
    [
        ("Error al enviar. Contacta a soporte", True),
        ("Cloudflare bloqueó esta sesión antes del envío", False),
    ],
)
def test_weekly_forms_does_not_retry_or_reserve_another_phone(
    tmp_path: Path, monkeypatch, message: str, submission_attempted: bool
):
    """Un rechazo o bloqueo registra una sola ejecución y un solo teléfono."""
    calls = []

    async def fake_run(self, config):
        calls.append(config)
        return {
            "status": "FAIL",
            "dry_run": False,
            "summary": message,
            "utel_submission_message": message,
            "utel_submission_attempted": submission_attempted,
            "utel_submission": "failed" if submission_attempted else "skipped",
            "lead_url": None,
            "lead_found": "failed",
            "stages": [],
            "screenshots": [],
        }

    monkeypatch.setattr(WeeklyFormsRunner, "run", fake_run)
    content = _workbook_bytes([
        ["Mexico", "Licenciatura", "https://utel.edu.mx/programa", "Form Lp", "QA", ""],
    ])
    mapping = WeeklyFormsSpreadsheetService().preview(content, "QA.xlsx")["sheets"][0]["mapping"]
    settings = Settings(
        database_path=tmp_path / "test.db",
        storage_dir=tmp_path / "storage",
        utel_test_phones_json='{"Mexico":["+525512345678","+525512345679"]}',
    )
    app = create_app(settings)
    job_id = "weekly-single-attempt"
    app.state.utel_batch_jobs[job_id] = {
        "status": "RUNNING", "total": 1, "completed": 0,
        "success": 0, "failed": 0, "pending": 0, "cancel_requested": False,
    }
    asyncio.run(_run_utel_batch_job(
        app, job_id, content, "QA.xlsx",
        {"automation_module": "weekly_forms", "lead_search_destination": "balanceador"},
        mapping,
    ))
    job = app.state.utel_batch_jobs[job_id]

    with get_connection(settings.database_path) as connection:
        reserved_count = connection.execute("SELECT COUNT(*) FROM test_leads").fetchone()[0]

    assert len(calls) == reserved_count == 1, job
    assert job["status"] == "FAIL"
    assert len(job["results"][0]["result"]["form_attempts"]) == 1
    report = load_workbook(settings.storage_dir / "reports" / "bot" / f"{job_id}_QA.xlsx")
    assert report["Datos del formulario"].max_row == 2
    if submission_attempted:
        assert "revisar antes de reenviar" in job["results"][0]["result"]["summary"]


def test_manual_form_failure_keeps_lead_cell_blank():
    content = _workbook_bytes([
        ["USA", "Licenciatura", "https://example.test/no-form", "Form Lp", "LatAm", ""],
    ])
    service = WeeklyFormsSpreadsheetService()
    preview = service.preview(content, "QA.xlsx")
    mapping = preview["sheets"][0]["mapping"]
    row = service.rows_for_mapping(content, mapping)[0]
    result = {
        "status": "FAIL",
        "dry_run": False,
        "lead_url": None,
        "lead_email": "persona@example.test",
        "selected_program_name": "",
        "utel_submission_attempted": False,
        "stages": [{"stage": "weekly_manual", "status": "FAIL", "message": "Sin formulario"}],
        "summary": "Completar manualmente",
    }

    workbook = BotReportService().build(content, mapping, [{"row": row, "result": result}])
    saved = io.BytesIO()
    workbook.save(saved)
    output = load_workbook(io.BytesIO(saved.getvalue()), data_only=True)
    assert output["QA"].cell(2, 6).value is None


def test_generic_lp_form_is_identified_and_filled(tmp_path: Path):
    async def scenario():
        from playwright.async_api import async_playwright

        settings = Settings(database_path=tmp_path / "test.db", storage_dir=tmp_path / "storage")
        runner = WeeklyFormsRunner(settings)
        config = WeeklyFormsCaseConfig.model_validate({
            "name": "Weekly Forms test",
            "environment": "sandbox",
            "dry_run": True,
            "country": "USA",
            "utel_url": "https://example.test/form",
            "modality": "En linea",
            "level": "Licenciatura",
            "form_type": "lateral",
            "weekly_form_type": "form_lp",
            "workflow_mode": "form_validation",
            "lead": {"name": "Persona QA", "email": "persona@example.test", "phone": "2125550199"},
        })
        runner._rotation_config = config
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.set_content("""
              <form id="lead-form">
                <label>Nombre <input name="name" required></label>
                <label>Email <input name="email" type="email" required></label>
                <label>Teléfono <input name="phone" type="tel" required></label>
                <label>Área de interés <select name="area" required><option value="">Selecciona</option><option value="lic">Licenciatura</option></select></label>
                <label>Programa <select name="program" required><option value="">Selecciona</option><option value="adm">Administración</option></select></label>
                <label>Privacidad <input name="privacy" type="checkbox" required></label>
                <button type="submit">Solicitar información</button>
              </form>
            """)
            form = await runner._find_utel_form(page, config)
            await runner._fill_utel_form(page, form, config)
            assert await form.locator('[name="name"]').input_value() == "Persona QA"
            assert await form.locator('[name="email"]').input_value() == "persona@example.test"
            assert await form.locator('[name="phone"]').input_value() == "2125550199"
            assert await form.locator('[name="area"]').input_value() == "lic"
            assert await form.locator('[name="program"]').input_value() == "adm"
            assert await form.locator('[name="privacy"]').is_checked()
            await browser.close()

    asyncio.run(scenario())


def test_colombian_document_and_country_selection_are_corrected(tmp_path: Path):
    """Weekly Forms fills the QA document and replaces a wrong default country."""

    async def scenario():
        from playwright.async_api import async_playwright

        runner = WeeklyFormsRunner(Settings(database_path=tmp_path / "test.db", storage_dir=tmp_path / "storage"))
        config = WeeklyFormsCaseConfig.model_validate({
            "country": "Colombia",
            "utel_url": "https://example.test/colombia/form",
            "modality": "En linea",
            "level": "Licenciatura",
            "weekly_form_type": "form_lp",
            "qa_document_required": True,
            "workflow_mode": "form_validation",
            "lead": {
                "name": "Persona QA",
                "email": "persona@example.test",
                "phone": "3001234567",
                "document_number": "QA-20260925-000001",
            },
        })
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.set_content("""
              <form>
                <label>País <select name="country">
                  <option value="mx" selected>México (+52)</option>
                  <option value="co">Colombia (+57)</option>
                </select></label>
                <label>Número de documento <input id="numeroDocumento_input" required></label>
              </form>
            """)
            form = page.locator("form")
            await runner._fill_document_number(form, config)
            await runner._select_semantic_option(form.locator('[name="country"]'), "Colombia", "country")
            assert await form.locator("#numeroDocumento_input").input_value() == "QA-20260925-000001"
            assert await form.locator('[name="country"]').input_value() == "co"
            await browser.close()

    asyncio.run(scenario())


def test_page_without_lead_form_is_reported_for_manual_work(tmp_path: Path):
    async def scenario():
        from playwright.async_api import async_playwright

        runner = WeeklyFormsRunner(Settings(database_path=tmp_path / "test.db", storage_dir=tmp_path / "storage"))
        runner.GENERIC_FORM_TIMEOUT_MS = 50
        config = WeeklyFormsCaseConfig.model_validate({
            "country": "Mexico", "utel_url": "https://example.test/no-form",
            "modality": "En linea", "level": "Licenciatura", "form_type": "lateral",
            "weekly_form_type": "form_lp", "workflow_mode": "form_validation",
            "lead": {"name": "Persona QA", "email": "persona@example.test", "phone": "5551234567"},
        })
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.set_content("<main><h1>Contenido sin formulario</h1></main>")
            try:
                await runner._find_utel_form(page, config)
                raise AssertionError("Se esperaba UtelQaError")
            except UtelQaError as error:
                assert error.stage == "weekly_manual"
                assert "se dejará en blanco" in str(error)
            await browser.close()

    asyncio.run(scenario())


def test_custom_privacy_checkbox_is_activated(tmp_path: Path):
    async def scenario():
        from playwright.async_api import async_playwright

        runner = WeeklyFormsRunner(Settings(database_path=tmp_path / "test.db", storage_dir=tmp_path / "storage"))
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.set_content("""
              <input id="terms" type="checkbox">
              <label for="terms">Acepto la política de privacidad</label>
              <script>document.querySelector('#terms').addEventListener('click', event => event.preventDefault())</script>
            """)
            checkbox = page.locator("#terms")
            await runner._ensure_checkbox_checked(checkbox)
            assert await checkbox.is_checked()
            await browser.close()

    asyncio.run(scenario())


def test_parallel_crm_uses_the_first_detail_as_primary_result(tmp_path: Path):
    """Weekly Forms conserva como enlace principal el CRM que responde primero."""

    async def scenario():
        runner = WeeklyFormsRunner(Settings(database_path=tmp_path / "test.db", storage_dir=tmp_path / "storage"))
        runner._submission_attempted = True
        inconcert_url = "https://crm.test/inconcert/contact/1"
        balancer_url = "https://lead-balancer.scalahed.com/leads/detail/2"

        # Las páginas aisladas representan las dos pestañas que usa el flujo
        # paralelo. El detalle del Balanceador termina antes que InConcert.
        inconcert_page = Mock(url="https://crm.test/inconcert/contacts")
        balancer_page = Mock(url="https://lead-balancer.scalahed.com/leads/")
        inconcert_page.set_default_timeout = Mock()
        balancer_page.set_default_timeout = Mock()
        context = Mock(new_page=AsyncMock(side_effect=[inconcert_page, balancer_page]))

        async def run_stage(_number, _stage, _message, _page, action, _screenshot=None):
            return await action()

        async def search_inconcert(_page, _email, _name):
            await asyncio.sleep(0.04)

        async def search_balancer(_page, _email, _name):
            await asyncio.sleep(0.01)
            runner.lead_url = balancer_url

        async def open_manage(_page, _name, _email):
            await asyncio.sleep(0.02)
            runner.lead_url = inconcert_url
            return Mock(url=inconcert_url)

        runner._run_stage = run_stage
        runner._open_inconcert = AsyncMock()
        runner._login_inconcert = AsyncMock()
        runner._open_contacts = AsyncMock()
        runner._search_lead = search_inconcert
        runner._search_lead_balancer = search_balancer
        runner._open_manage = open_manage

        config = WeeklyFormsCaseConfig.model_validate({
            "name": "Weekly Forms first CRM",
            "environment": "sandbox",
            "country": "Mexico",
            "utel_url": "https://utel.edu.mx/programa",
            "inconcert_url": "https://crm.test",
            "modality": "En linea",
            "level": "Licenciatura",
            "workflow_mode": "form_validation",
            "lead": {"name": "Persona QA", "email": "persona@example.test", "phone": "5551234567"},
        })

        result = await runner._verify_crm_parallel(
            context,
            config,
            None,
            "2026-09-15T10:00:00",
            0.0,
        )

        assert result["inconcert_lead_url"] == inconcert_url
        assert result["balancer_lead_url"] == balancer_url
        assert result["lead_url"] == balancer_url
        assert result["lead_source"] == "balanceador"
        assert result["source_final"] == "balanceador"
        assert result["first_crm_source"] == "balanceador"

    asyncio.run(scenario())


def test_parallel_crm_records_both_failures_and_does_not_claim_a_verified_link(tmp_path: Path):
    """Si ambos CRM no confirman el lead, el reporte falla con trazas explícitas."""

    async def scenario():
        runner = WeeklyFormsRunner(Settings(database_path=tmp_path / "test.db", storage_dir=tmp_path / "storage"))
        runner._submission_attempted = True
        inconcert_page = Mock(url="https://crm.test/inconcert/contacts")
        balancer_page = Mock(url="https://lead-balancer.scalahed.com/leads/")
        inconcert_page.set_default_timeout = Mock()
        balancer_page.set_default_timeout = Mock()
        context = Mock(new_page=AsyncMock(side_effect=[inconcert_page, balancer_page]))

        async def run_stage(_number, _stage, _message, _page, action, _screenshot=None):
            # Imitar la excepción real de una etapa; el wrapper paralelo es
            # responsable de conservarla antes de continuar con el otro CRM.
            return await action()

        async def not_found(stage, _page, *_args):
            raise UtelQaError(stage, "El lead no aparece en el CRM.")

        runner._run_stage = run_stage
        runner._open_inconcert = AsyncMock()
        runner._login_inconcert = AsyncMock()
        runner._open_contacts = AsyncMock()
        runner._search_lead = lambda page, email, name: not_found("inconcert_search", page, email, name)
        runner._search_lead_balancer = lambda page, email, name: not_found("lead_balancer_search", page, email, name)

        config = WeeklyFormsCaseConfig.model_validate({
            "name": "Weekly Forms CRM sin resultados",
            "environment": "production",
            "dry_run": False,
            "country": "Mexico",
            "utel_url": "https://utel.edu.mx/programa",
            "inconcert_url": "https://crm.test",
            "modality": "En linea",
            "level": "Licenciatura",
            "workflow_mode": "form_validation",
            "lead": {"name": "Persona QA", "email": "persona@example.test", "phone": "5551234567"},
        })

        result = await runner._verify_crm_parallel(
            context,
            config,
            None,
            "2026-09-24T10:00:00",
            0.0,
        )

        failed_stages = {stage.stage for stage in result["stages"] if stage.status == "FAIL"}
        assert failed_stages == {"inconcert_search", "lead_balancer_search"}
        assert result["lead_found"] == "failed"
        assert result["lead_url"] is None
        assert result["status"] == "FAIL"
        assert "no se encontró ni se pudo verificar" in result["summary"]
        assert "enlace del lead verificado" not in result["summary"]

    asyncio.run(scenario())


def test_parallel_crm_keeps_success_when_one_crm_finds_lead(tmp_path: Path):
    """Un resultado confirmado sigue siendo suficiente si el otro CRM falla."""

    async def scenario():
        runner = WeeklyFormsRunner(Settings(database_path=tmp_path / "test.db", storage_dir=tmp_path / "storage"))
        runner._submission_attempted = True
        balancer_url = "https://lead-balancer.scalahed.com/leads/detail/3"
        inconcert_page = Mock(url="https://crm.test/inconcert/contacts")
        balancer_page = Mock(url="https://lead-balancer.scalahed.com/leads/")
        inconcert_page.set_default_timeout = Mock()
        balancer_page.set_default_timeout = Mock()
        context = Mock(new_page=AsyncMock(side_effect=[inconcert_page, balancer_page]))

        async def run_stage(_number, _stage, _message, _page, action, _screenshot=None):
            return await action()

        async def fail_inconcert(_page, _email, _name):
            raise UtelQaError("inconcert_search", "InConcert no confirmó el lead.")

        async def find_balancer(_page, _email, _name):
            runner.lead_url = balancer_url

        runner._run_stage = run_stage
        runner._open_inconcert = AsyncMock()
        runner._login_inconcert = AsyncMock()
        runner._open_contacts = AsyncMock()
        runner._search_lead = fail_inconcert
        runner._search_lead_balancer = find_balancer

        config = WeeklyFormsCaseConfig.model_validate({
            "name": "Weekly Forms CRM parcial",
            "environment": "production",
            "dry_run": False,
            "country": "Mexico",
            "utel_url": "https://utel.edu.mx/programa",
            "inconcert_url": "https://crm.test",
            "modality": "En linea",
            "level": "Licenciatura",
            "workflow_mode": "form_validation",
            "lead": {"name": "Persona QA", "email": "persona@example.test", "phone": "5551234567"},
        })

        result = await runner._verify_crm_parallel(
            context,
            config,
            None,
            "2026-09-24T10:00:00",
            0.0,
        )

        assert result["status"] == "PASS"
        assert result["lead_url"] == balancer_url
        assert result["first_crm_source"] == "balanceador"
        assert any(stage.stage == "inconcert_search" and stage.status == "FAIL" for stage in result["stages"])

    asyncio.run(scenario())
