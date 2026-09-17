import asyncio

import pytest

from backend.app.modules.strapi_products.balancer_catalog import (
    BalancerCatalogError,
    BalancerProgramCatalog,
    _is_manual_challenge,
    program_lookup_details,
    select_catalog_code,
)


def test_program_lookup_uses_base_name_and_preserves_degree_for_matching():
    assert program_lookup_details("Licenciatura en Educación para la Sustentabilidad") == (
        "Educación para la Sustentabilidad",
        "licenciatura",
    )
    assert program_lookup_details("Maestría en Educación para la Sustentabilidad") == (
        "Educación para la Sustentabilidad",
        "maestria",
    )
    assert program_lookup_details("Doctorado Educación para la Sustentabilidad") == (
        "Educación para la Sustentabilidad",
        "doctorado",
    )


def test_select_catalog_code_matches_base_name_and_degree():
    rows = [
        ["20261591", "Educación para la Sustentabilidad", "LICENCIATURA"],
        ["20271591", "Educación para la Sustentabilidad", "MASTER"],
        ["20260001", "Educación para otra cosa", "LICENCIATURA"],
    ]
    assert select_catalog_code(rows, "Maestría en Educación para la Sustentabilidad") == "20271591"


def test_select_catalog_code_rejects_ambiguous_matches():
    rows = [
        ["100", "Educación para la Sustentabilidad", "LICENCIATURA"],
        ["101", "Educación para la Sustentabilidad", "LICENCIATURA"],
    ]
    with pytest.raises(BalancerCatalogError, match="varios códigos"):
        select_catalog_code(rows, "Licenciatura en Educación para la Sustentabilidad")


def test_manual_challenge_is_detected_without_attempting_to_bypass_it():
    assert _is_manual_challenge(
        "https://lead-balancer.scalahed.com/login/?__cf_chl_rt_tk=token",
        "Just a moment...",
        "",
    )
    assert not _is_manual_challenge(
        "https://lead-balancer.scalahed.com/catalog/program-of-interest",
        "Catalogo de Programas de interes",
        "Buscar",
    )


def test_catalog_search_uses_base_name_and_returns_matching_code():
    class FakeLocator:
        def __init__(self, *, rows=None):
            self.rows = rows or []
            self.value = None
            self.pressed = None
            self.first = self

        async def wait_for(self, **kwargs):
            return None

        async def fill(self, value):
            self.value = value

        async def press(self, value):
            self.pressed = value

        async def evaluate_all(self, script):
            return self.rows

    class FakePage:
        url = "https://lead-balancer.scalahed.com/catalog/program-of-interest"

        def __init__(self):
            self.search = FakeLocator()
            self.table = FakeLocator(rows=[
                ["20261591", "Educación para la Sustentabilidad", "LICENCIATURA"],
            ])

        def locator(self, selector):
            if selector.startswith("input[type='search']"):
                return self.search
            return self.table

    async def run():
        catalog = BalancerProgramCatalog("https://lead-balancer.scalahed.com/leads/")
        page = FakePage()
        catalog.page = page
        catalog.start = async_noop
        code = await catalog.get_siu_key("Licenciatura en Educación para la Sustentabilidad")
        assert code == "20261591"
        assert page.search.value == "Educación para la Sustentabilidad"
        assert page.search.pressed == "Enter"

    async def async_noop():
        return None

    asyncio.run(run())
