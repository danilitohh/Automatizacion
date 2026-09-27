"""Regresiones del tenant InConcert compartido por Filipinas, India y Singapur."""

import pytest

from backend.app.modules.bot_nuevos_productos.spreadsheet_service import (
    BotSpreadsheetService as NewProductsSpreadsheetService,
)
from backend.app.modules.weekly_auto.weekly_forms.spreadsheet_service import (
    WeeklyFormsSpreadsheetService,
)
from backend.app.modules.weekly_auto.weekly_leads.spreadsheet_service import (
    WeeklyLeadsSpreadsheetService,
)
from backend.app.services.bot_spreadsheet_service import BotSpreadsheetService
from backend.app.services.leads_deploy_spreadsheet_service import (
    LeadsDeploySpreadsheetService,
)


SINGAPORE_URL = "https://mas-utel-singapur.infunnel.inconcert.cloud/"
EMERGING_URL = "https://mas-utel-emergentes.inconcertcc.com/mas/contact/people"


@pytest.mark.parametrize(
    "service",
    (
        BotSpreadsheetService,
        NewProductsSpreadsheetService,
        LeadsDeploySpreadsheetService,
        WeeklyFormsSpreadsheetService,
        WeeklyLeadsSpreadsheetService,
    ),
)
@pytest.mark.parametrize(
    "country", ("Filipinas", "Philippines", "India", "Singapur", "Singapore")
)
def test_asian_country_aliases_use_singapore_inconcert(service, country):
    """Ningún alias asiático debe activar el fallback de Emergentes."""

    assert service.default_inconcert_url(country) == SINGAPORE_URL


@pytest.mark.parametrize("service", (BotSpreadsheetService, WeeklyFormsSpreadsheetService))
def test_outdated_excel_hint_does_not_override_asian_country(service):
    """Un enlace antiguo del Excel no puede desviar Filipinas a Emergentes."""

    assert service.inconcert_url_for_case(
        "Philippines", EMERGING_URL, EMERGING_URL
    ) == SINGAPORE_URL


def test_other_countries_keep_explicit_excel_hint():
    """La prioridad histórica de los demás mercados permanece sin cambios."""

    assert BotSpreadsheetService.inconcert_url_for_case(
        "Colombia", "https://crm.example.test/custom", EMERGING_URL
    ) == "https://crm.example.test/custom"


@pytest.mark.parametrize(
    ("level", "expected"),
    (
        ("Philippines Bachelor", "Filipinas"),
        ("Filipinas Master", "Filipinas"),
        ("India Master", "India"),
        ("Singapore Bachelor", "Singapur"),
    ),
)
def test_weekly_forms_resolves_country_from_global_level(level, expected):
    """La columna Global no oculta el país declarado en el nivel."""

    assert WeeklyFormsSpreadsheetService.effective_country(
        "Global", level, "https://utel.edu.mx/global/"
    ) == expected
