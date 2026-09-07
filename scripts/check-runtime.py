"""Check imports and launch the installed browser without external requests."""
import importlib
from playwright.sync_api import sync_playwright

for module in (
    'fastapi', 'uvicorn', 'pydantic_settings', 'httpx', 'cloudscraper',
    'openpyxl', 'docx', 'multipart', 'pypdf', 'phonenumbers',
):
    importlib.import_module(module)

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page()
    page.set_content('<title>UTEL setup check</title>')
    assert page.title() == 'UTEL setup check'
    browser.close()
