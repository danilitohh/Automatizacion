import asyncio
import json

from playwright.async_api import async_playwright


URLS = [
    "https://utel.edu.mx/argentina/licenciatura-en-arquitectura",
    "https://utel.edu.mx/argentina/licenciatura-en-ingenieria-en-programacion-en-la-nube",
]


async def main() -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1600, "height": 1000})
        for url in URLS:
            await page.goto(url, wait_until="domcontentloaded", timeout=90000)
            await page.wait_for_timeout(5000)
            result = await page.evaluate(
                """() => {
                  const form = [...document.querySelectorAll('form')].find(candidate =>
                    candidate.querySelector('[data-cy="productsInput"]') &&
                    candidate.querySelector('button[type="submit"], input[type="submit"]')
                  );
                  if (!form) return { error: 'form not found', title: document.title };
                  const fields = [...form.querySelectorAll('input, select, textarea')].map(el => ({
                    tag: el.tagName,
                    type: el.getAttribute('type'),
                    name: el.getAttribute('name'),
                    id: el.id,
                    dataCy: el.getAttribute('data-cy'),
                    value: el.value,
                    placeholder: el.getAttribute('placeholder'),
                    checked: el.checked,
                    disabled: el.disabled,
                    options: el.tagName === 'SELECT' && el.getAttribute('data-cy') !== 'countryCallingCode'
                      ? [...el.options].map(o => ({text:o.textContent.trim(), value:o.value, selected:o.selected}))
                      : undefined,
                  }));
                  return {
                    title: document.title,
                    action: form.action,
                    fields,
                    h1: document.querySelector('h1')?.textContent?.trim(),
                  };
                }"""
            )
            print("URL=" + url)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
