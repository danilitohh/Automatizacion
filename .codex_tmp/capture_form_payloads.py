import asyncio
import json

from playwright.async_api import Route, async_playwright


URLS = [
    "https://utel.edu.mx/argentina/licenciatura-en-arquitectura",
    "https://utel.edu.mx/argentina/licenciatura-en-ingenieria-en-programacion-en-la-nube",
]


async def main() -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        for url in URLS:
            page = await browser.new_page(viewport={"width": 1600, "height": 1000})
            captured: list[dict] = []

            async def intercept(route: Route) -> None:
                request = route.request
                if request.method == "POST" and request.url.rstrip("/").endswith("/api/forms"):
                    try:
                        payload = request.post_data_json
                    except Exception:
                        payload = request.post_data
                    captured.append({"url": request.url, "payload": payload})
                    await route.abort("blockedbyclient")
                    return
                await route.continue_()

            await page.route("**/*", intercept)
            await page.goto(url, wait_until="domcontentloaded", timeout=90000)
            await page.wait_for_timeout(5000)
            form = page.locator("form").filter(has=page.locator('[data-cy="productsInput"]')).first
            await form.locator('[data-cy="textfieldInput"]').fill("Diagnostico Payload")
            await form.locator('[data-cy="emailInput"]').fill("diagnostico.payload@example.com")
            await form.locator('[data-cy="telephoneInput"]').fill("1142345678")

            selects = form.locator("select")
            for index in range(await selects.count()):
                select = selects.nth(index)
                data_cy = (await select.get_attribute("data-cy") or "").lower()
                name = (await select.get_attribute("name") or "").lower()
                if data_cy in {"educationlevelinput", "countrycallingcode", "productsinput"}:
                    continue
                if any(word in f"{data_cy} {name}" for word in ("city", "ciudad", "province", "provincia")):
                    options = select.locator("option")
                    for option_index in range(await options.count()):
                        option = options.nth(option_index)
                        value = await option.get_attribute("value") or ""
                        if value.strip():
                            await select.select_option(value=value)
                            break

            checkboxes = form.locator('input[type="checkbox"]')
            for index in range(await checkboxes.count()):
                checkbox = checkboxes.nth(index)
                if await checkbox.is_visible() and not await checkbox.is_checked():
                    await checkbox.evaluate("el => el.click()")

            await form.locator('button[type="submit"], input[type="submit"]').evaluate("el => el.click()")
            deadline = asyncio.get_running_loop().time() + 20
            while not captured and asyncio.get_running_loop().time() < deadline:
                await page.wait_for_timeout(250)
            print("URL=" + url)
            print(json.dumps(captured, ensure_ascii=False, indent=2, sort_keys=True))
            await page.close()
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
