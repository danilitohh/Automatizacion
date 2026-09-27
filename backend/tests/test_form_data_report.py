"""Pruebas de la evidencia de formularios en los reportes descargables."""

from __future__ import annotations

import asyncio
from io import BytesIO

from openpyxl import Workbook, load_workbook

from backend.app.api.routes import _form_attempt_record, _merge_utel_and_crm_results
from backend.app.modules.bot_leads_deploy.report_service import BotReportService as LeadsReportService
from backend.app.modules.bot_nuevos_productos.report_service import BotReportService as ProductsReportService
from backend.app.modules.form_validation.report_service import FormValidationReportService
from backend.app.services.form_field_evidence import capture_visible_form_fields


def _source() -> bytes:
    """Crea una matriz mínima sin depender de sitios externos."""

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "QA"
    sheet.append(["Country", "Nivel", "Activo de Test", "Lead"])
    sheet.append(["Colombia", "Licenciatura", "https://utel.edu.mx/colombia/", ""])
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def _result() -> dict:
    """Representa un reintento con dos teléfonos y un documento visible."""

    first = {
        "attempt": 1,
        "lead_name": "Persona QA A",
        "lead_email": "qa-a@example.test",
        "lead_phone": "0012345678",
        "form_filled": True,
        "utel_submission_attempted": True,
        "utel_submission": "failed",
        "status": "FAIL",
        "error": "UTEL rechazó el primer intento",
        "form_fields": [{"key": "documento", "label": "Documento", "value": "1000000019"}],
    }
    second = {
        "attempt": 2,
        "lead_name": "Persona QA B",
        "lead_email": "qa-b@example.test",
        "lead_phone": "0012345679",
        "form_filled": True,
        "utel_submission_attempted": True,
        "utel_submission": "success",
        "status": "PASS",
        "form_fields": [{"key": "documento", "label": "Documento", "value": "=1+1"}],
    }
    return {
        "status": "PASS",
        "workflow_mode": "form_validation",
        "country": "Colombia",
        "level": "Licenciatura",
        "lead_name": second["lead_name"],
        "lead_email": second["lead_email"],
        "lead_phone": second["lead_phone"],
        "utel_submission_attempted": True,
        "utel_submission": "success",
        "selected_program_name": "Administración",
        "lead_url": "https://crm.test/lead/2",
        "form_fields": second["form_fields"],
        "form_attempts": [first, second],
        "stages": [{"stage": "utel_open", "status": "PASS", "url": "https://utel.edu.mx/colombia/"}],
    }


def test_all_report_modules_include_form_values_and_every_retry():
    """Los cuatro módulos comparten la misma hoja sin perder un intento previo."""

    row = {"sheet": "QA", "row_number": 2, "utel_url": "https://utel.edu.mx/colombia/"}
    item = {"row": row, "result": _result()}
    for report_cls in (ProductsReportService, LeadsReportService, FormValidationReportService):
        workbook = report_cls().build(_source(), {"utel_url": "Activo de Test"}, [item])
        saved = BytesIO()
        workbook.save(saved)
        reopened = load_workbook(BytesIO(saved.getvalue()))
        audit = reopened["Datos del formulario"]
        headers = {cell.value: cell.column for cell in audit[1]}
        assert audit.max_row == 3
        assert [audit.cell(row_number, headers["Teléfono"]).value for row_number in (2, 3)] == [
            "0012345678", "0012345679"
        ]
        assert audit.cell(2, headers["Error"]).value == "UTEL rechazó el primer intento"
        assert audit.cell(3, headers["Campo: Documento"]).value == "=1+1"
        assert audit.cell(3, headers["Campo: Documento"]).data_type == "s"
        assert audit.cell(2, headers["Estado llenado"]).value == "Rellenado"
        assert reopened["QA"]["A2"].value == "Colombia"
        if report_cls is FormValidationReportService:
            assert "Form Validation resultados" in reopened.sheetnames


def test_failed_before_fill_is_not_presented_as_a_completed_form():
    """Una fila con datos generados, pero sin formulario, queda distinguible."""

    row = {"sheet": "QA", "row_number": 2, "utel_url": "https://utel.edu.mx/colombia/"}
    result = {
        "status": "FAIL",
        "lead_name": "Persona QA",
        "lead_email": "qa@example.test",
        "lead_phone": "0012345678",
        "utel_submission_attempted": False,
        "stages": [{"stage": "utel_form", "status": "FAIL", "message": "Sin formulario"}],
        "summary": "Sin formulario",
    }
    workbook = LeadsReportService().build(_source(), {}, [{"row": row, "result": result}])
    audit = workbook["Datos del formulario"]
    headers = {cell.value: cell.column for cell in audit[1]}
    assert audit.cell(2, headers["Estado llenado"]).value == "No confirmado"
    assert audit.cell(2, headers["Envío intentado"]).value == "No"
    assert audit.cell(2, headers["Nombre"]).value == "Persona QA"


def test_crm_merge_preserves_original_form_evidence():
    """La fase CRM no debe borrar los valores leídos antes del envío."""

    submission = _result()
    verification = {"status": "PASS", "lead_url": "https://crm.test/lead/2", "stages": [], "screenshots": []}
    submission["screenshots"] = []
    merged = _merge_utel_and_crm_results(submission, verification)
    assert merged["form_fields"] == submission["form_fields"]
    assert merged["form_attempts"] == submission["form_attempts"]


def test_attempt_snapshot_preserves_generated_data_if_form_did_not_open():
    """El registro de un fallo previo al llenado no inventa campos capturados."""

    from types import SimpleNamespace

    config = SimpleNamespace(lead=SimpleNamespace(name="Persona QA", email="qa@example.test", phone="0012345678"))
    snapshot = _form_attempt_record({"status": "FAIL", "summary": "Sin formulario", "stages": []}, config, 1)
    assert snapshot["form_filled"] is False
    assert snapshot["lead_phone"] == "0012345678"
    assert snapshot["form_fields"] == []


def test_browser_capture_reads_visible_values_only():
    """La captura recoge selectores y privacidad, pero nunca tokens ni claves."""

    async def scenario() -> None:
        from playwright.async_api import async_playwright

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.set_content("""
                <form>
                  <label for="name">Nombre</label><input id="name" value="Persona QA">
                  <label for="level">Nivel</label><select id="level">
                    <option value="bachelor" selected>Licenciatura</option>
                  </select>
                  <label for="privacy">Privacidad</label><input id="privacy" type="checkbox" checked>
                  <input name="token" type="hidden" value="secret-token">
                  <input name="password" type="password" value="secret-password">
                </form>
            """)
            fields = await capture_visible_form_fields(page.locator("form"))
            await browser.close()
        values = {field["label"]: field["value"] for field in fields}
        assert values == {"Nombre": "Persona QA", "Nivel": "Licenciatura", "Privacidad": "Sí"}

    asyncio.run(scenario())
