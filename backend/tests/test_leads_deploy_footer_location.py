"""Regresión del formulario inferior sin id publicado por UTEL Colombia."""

import asyncio

from playwright.async_api import async_playwright

from backend.app.automations.leads_deploy.runner import LeadsDeployRunner
from backend.app.config.settings import Settings
from backend.app.schemas.bot import UtelQaConfig, UtelLead


def test_footer_without_id_is_located_and_requeried_after_remount():
    async def scenario():
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(channel="chrome", headless=True)
            try:
                page = await browser.new_page(viewport={"width": 1440, "height": 900})
                await page.route("https://example.com/**", lambda route: route.fulfill(body="<html></html>", content_type="text/html"))
                await page.goto("https://example.com/colombia/programa")
                fields = '<input data-cy="emailInput"><input data-cy="telephoneInput"><select data-cy="productsInput"><option>Programa</option></select>'
                for identifier in ('', 'id="FooterBLC"'):
                    await page.set_content(
                        '<header style="position:fixed;top:0;height:100px">Menú</header>'
                        f'<form id="TarjetaBLC">{fields}</form><form id="LateralBLC" hidden>{fields}</form>'
                        '<div style="height:1600px"></div>'
                        f'<div class="form-container-config-chakra-config"><form {identifier} style="height:400px">{fields}</form></div>'
                        '<div style="height:1800px">Preguntas frecuentes y pie legal</div>'
                    )
                    runner = LeadsDeployRunner(Settings())
                    config = UtelQaConfig(country="Colombia", level="Licenciatura", modality="En linea", form_type="footer", utel_url=page.url, lead=UtelLead())
                    form = await runner._find_utel_form(page, config)
                    box = await form.bounding_box()
                    assert box and box["y"] >= 100
                    assert box["y"] + box["height"] <= 900
                    assert await form.get_attribute("id") not in {"TarjetaBLC", "LateralBLC"}
                    # El locator debe sobrevivir al reemplazo del nodo React.
                    await form.evaluate("element => element.replaceWith(element.cloneNode(true))")
                    await runner._footer_locator(page).locator('[data-cy="emailInput"]').fill("qa@example.com")
                    assert await runner._footer_locator(page).locator('[data-cy="emailInput"]').input_value() == "qa@example.com"
                    assert await page.locator('#TarjetaBLC [data-cy="emailInput"]').input_value() == ""
            finally:
                await browser.close()

    asyncio.run(scenario())


def test_program_heading_tolerates_safe_singular_plural_difference():
    assert LeadsDeployRunner._program_titles_equivalent(
        "bootcamp fundamento de ciencias de datos proyectos agiles con scrum",
        "bootcamp fundamentos de ciencias de datos proyectos agiles con scrum",
    )
    assert not LeadsDeployRunner._program_titles_equivalent(
        "bootcamp fundamento de ciencias de datos",
        "bootcamp fundamento de ciencias computacionales",
    )
