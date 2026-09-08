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
            field = page.locator('[data-cy="productsInput"]').first
            await field.wait_for(state="visible", timeout=30000)
            await page.wait_for_timeout(3000)
            before = await field.evaluate(
                """el => ({
                  attributes: [...el.attributes].reduce((a,x)=>(a[x.name]=x.value,a),{}),
                  parentClass: el.parentElement?.className,
                  grandparentClass: el.parentElement?.parentElement?.className,
                  siblingText: [...(el.parentElement?.children || [])].map(node => (node.innerText || node.textContent || '').trim()).filter(Boolean).slice(0, 20),
                  reactKeys: Object.keys(el).filter(key => key.startsWith('__react')).map(key => key.slice(0, 40)),
                })"""
            )
            await field.fill("")
            await field.type("Programación" if "programacion" in url else "Arquitectura", delay=50)
            await page.wait_for_timeout(2500)
            after = await page.evaluate(
                """() => ({
                  lists: [...document.querySelectorAll('[role="listbox"], [role="option"], [class*="menu" i], [class*="option" i], [data-cy*="product" i], ul li')]
                    .filter(el => el.getClientRects().length)
                    .map(el => ({tag:el.tagName, role:el.getAttribute('role'), id:el.id, cls:el.className, text:(el.innerText||el.textContent||'').trim(), attrs:[...el.attributes].reduce((a,x)=>(a[x.name]=x.value,a),{})}))
                    .filter(item => item.text)
                    .slice(0, 100)
                })"""
            )
            print("URL=" + url)
            print(json.dumps({"before": before, "after": after}, ensure_ascii=False, indent=2))
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
