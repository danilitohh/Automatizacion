"""Nivel académico de páginas QA con columna heredada inconsistente."""

import pytest

from backend.app.modules.weekly_auto.weekly_forms.spreadsheet_service import WeeklyFormsSpreadsheetService
from backend.app.modules.weekly_auto.weekly_leads.spreadsheet_service import WeeklyLeadsSpreadsheetService


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://universidad.utel.edu.mx/usa/maestrias-online/", "Maestría"),
        ("https://universidad.utel.edu.mx/dominicana/doctorados", "Doctorado"),
        ("https://utel.edu.mx/licenciaturas-hibridas", "Licenciatura"),
        ("https://universidad.utel.edu.mx/colombia/carreras-online", "Licenciatura"),
    ],
)
def test_form_validation_uses_unambiguous_url_level(url: str, expected: str) -> None:
    """El nivel inequívoco de la URL prevalece sobre la columna heredada."""

    assert WeeklyLeadsSpreadsheetService.infer_level("Licenciatura", url) == expected


def test_form_validation_corrects_reverse_mismatch() -> None:
    """Una landing de licenciatura no hereda erróneamente una maestría."""

    assert WeeklyLeadsSpreadsheetService.infer_level(
        "Maestrías Hibridas", "https://utel.edu.mx/licenciaturas-hibridas"
    ) == "Licenciatura"


def test_weekly_forms_keeps_original_level_rule() -> None:
    """La corrección específica no cambia el módulo Weekly Forms."""

    url = "https://universidad.utel.edu.mx/usa/maestrias-online/"
    assert WeeklyFormsSpreadsheetService.infer_level("Licenciatura", url) == "Licenciatura"
