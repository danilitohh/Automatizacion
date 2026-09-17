"""Pruebas del parser aislado de Leads Deploy."""

from io import BytesIO

from openpyxl import Workbook

from app.services.leads_deploy_spreadsheet_service import (
    LeadsDeploySpreadsheetService,
)


def _workbook_bytes() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Deploy"
    sheet.append(
        [
            "Responsable",
            "Country",
            "Nivel",
            "Activo de Test",
            "Location",
            "Locale",
            "Cliente",
            "Url Origen Lead",
            "Url Lead",
        ]
    )
    sheet.append(
        [
            "QA",
            "Perú",
            "Licenciatura",
            "",
            "Tarjeta",
            "Peru",
            "Portales LatAm",
            "https://lead-balancer.scalahed.com",
            "",
        ]
    )
    sheet.append(
        [
            "QA",
            "",
            "Maestría",
            "",
            "Lateral",
            "Peru",
            "Portales LatAm",
            "https://lead-balancer.scalahed.com",
            "",
        ]
    )

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def test_preview_accepts_blank_activo_de_test() -> None:
    service = LeadsDeploySpreadsheetService()
    preview = service.preview(_workbook_bytes(), "Leads Deploy.xlsx")

    assert len(preview["sheets"]) == 1
    assert len(preview["sheets"][0]["rows"]) == 2
    assert "utel_url" not in preview["sheets"][0]["mapping"]


def test_rows_for_mapping_does_not_require_program_url() -> None:
    service = LeadsDeploySpreadsheetService()
    rows = service.rows_for_mapping(
        _workbook_bytes(),
        {
            "country": "Country",
            "level": "Nivel",
            "form_type": "Location",
            "lead_origin_url": "Url Origen Lead",
            "lead_url": "Url Lead",
            "workflow_mode": "form_validation",
        },
    )

    assert len(rows) == 2
    assert rows[0]["country"] == "Perú"
    assert rows[1]["country"] == "Perú"
    assert rows[0]["utel_url"] == ""
    assert rows[1]["workflow_mode"] == "form_validation"


def test_navigation_plan_normalizes_english_master_for_local_forms() -> None:
    """Master debe conservar el nivel de posgrado en formularios en español."""

    plan = LeadsDeploySpreadsheetService.deploy_navigation_plan("Master", "Mexico")

    assert plan["modality"] == "En linea"
    assert plan["level"] == "Maestria"
    assert plan["navigation_level"] == "Maestrias"


def test_navigation_plan_keeps_international_master_surface() -> None:
    """Los mercados internacionales siguen usando Master's Degree."""

    plan = LeadsDeploySpreadsheetService.deploy_navigation_plan("Master", "Filipinas")

    assert plan["modality"] == "Online"
    assert plan["level"] == "Master's Degree"
    assert plan["navigation_level"] == "Master"
