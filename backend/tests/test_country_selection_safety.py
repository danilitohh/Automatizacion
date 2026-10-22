"""Protecciones para no enviar un lead con el país de otra landing."""

from __future__ import annotations

import asyncio

import pytest

from backend.app.config.settings import Settings
from backend.app.modules.bot_leads_deploy.runner import UtelInconcertRunner, UtelQaError


def test_global_form_updates_both_country_controls() -> None:
    """Un país preseleccionado distinto debe cambiarse en ambos selectores."""

    async def scenario() -> None:
        from playwright.async_api import async_playwright

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.set_content("""
                <form>
                  <select name="paisesPIVI">
                    <option value="philippines" selected>Philippines</option>
                    <option value="india">India</option>
                  </select>
                  <select data-cy="countryCallingCode">
                    <option value="philippines" selected>Philippines</option>
                    <option value="india">India</option>
                  </select>
                </form>
            """)
            form = page.locator("form")
            await UtelInconcertRunner(Settings())._set_country_if_possible(form, "India")
            assert await form.locator('[name="paisesPIVI"]').input_value() == "india"
            assert await form.locator('[data-cy="countryCallingCode"]').input_value() == "india"
            await browser.close()

    asyncio.run(scenario())


def test_fixed_wrong_country_stops_before_submit() -> None:
    """Un país bloqueado e incorrecto no puede considerarse formulario listo."""

    async def scenario() -> None:
        from playwright.async_api import async_playwright

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.set_content("""
                <form><select data-cy="countryCallingCode" disabled>
                  <option value="philippines" selected>Philippines</option>
                  <option value="india">India</option>
                </select></form>
            """)
            with pytest.raises(UtelQaError, match="no permite cambiarlo"):
                await UtelInconcertRunner(Settings())._set_country_if_possible(page.locator("form"), "India")
            await browser.close()

    asyncio.run(scenario())
