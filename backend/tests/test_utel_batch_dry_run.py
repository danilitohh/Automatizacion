import io
import json

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook

from backend.app.automations.utel_inconcert.runner import UtelInconcertRunner
from backend.app.config.settings import Settings
from backend.app.main import create_app


@pytest.mark.parametrize("dry_run", [True, False, None])
def test_batch_preserves_safe_mode_and_marks_excel(tmp_path, monkeypatch, dry_run):
    seen = []

    async def fake_run(self, config):
        seen.append(config)
        return {"status": "PASS", "dry_run": config.dry_run, "stages": [], "summary": "Prueba local",
                "lead_url": None if config.dry_run else "https://crm.test/mas/contact/people/view/123"}

    monkeypatch.setattr(UtelInconcertRunner, "run", fake_run)
    workbook = Workbook()
    workbook.active.append(["Nivel", "URL", "Location", "Locale"])
    workbook.active.append(["Licenciatura", "https://example.test", "footer", "Mexico"])
    workbook.active.append(["Maestria", "https://example.test", "lateral", "Mexico"])
    content = io.BytesIO()
    workbook.save(content)
    config = {"lead": {}}
    if dry_run is not None:
        config["dry_run"] = dry_run
    mapping = {"level": "Nivel", "utel_url": "URL", "form_type": "Location", "country": "Locale",
               "selected_sheet": "Sheet", "selected_row_number": 3}
    app = create_app(
        Settings(
            database_path=tmp_path / "test.db",
            storage_dir=tmp_path / "storage",
            batch_delay_seconds=0,
        )
    )
    with TestClient(app) as client:
        response = client.post('/api/bots/utel-inconcert/batch-run',
                               data={"config": json.dumps(config), "mapping": json.dumps(mapping)},
                               files={"file": ("test.xlsx", content.getvalue())})
        assert response.status_code == 202, response.text
        job_id = response.json()["job_id"]
        job = client.get(f'/api/bots/utel-inconcert/batch/{job_id}').json()
        assert job["status"] == "PASS", job
        assert job["completed"] == job["total"] == 1
        assert len(seen) == 1
        assert seen[0].dry_run is (dry_run is not False)
        assert seen[0].level == "Maestria"
        assert seen[0].source_filename == "test.xlsx"
        report = client.get(job["download_url"])
    sheet = load_workbook(io.BytesIO(report.content)).active
    assert sheet.cell(2, 5).value is None
    assert sheet.cell(3, 5).value == ("EXITOSO" if dry_run is False else "DRY RUN - NO ENVIADO")
    assert sheet.cell(1, 7).value == "URL LEAD"
    assert sheet.cell(3, 7).value == ("https://crm.test/mas/contact/people/view/123" if dry_run is False else None)
    if dry_run is False:
        assert sheet.cell(3, 7).hyperlink.target == sheet.cell(3, 7).value


def test_each_batch_row_uses_its_country_crm_not_a_stale_url(tmp_path, monkeypatch):
    seen = []

    async def fake_run(self, config):
        seen.append((config.country, config.inconcert_url))
        return {"status": "PASS", "dry_run": True, "stages": [], "summary": "Prueba local"}

    monkeypatch.setattr(UtelInconcertRunner, "run", fake_run)
    countries = [("México", "mas-utel"), ("Argentina", "mas-utel-arg"),
                 ("Colombia", "mas-utel-col"), ("Perú", "mas-utel-pe"),
                 ("Ecuador", "mas-utel-ec")]
    workbook = Workbook()
    workbook.active.append(["Nivel", "URL", "Location", "Locale", "CRM"])
    for country, _ in countries:
        workbook.active.append(["Licenciatura", "https://example.test", "footer", country, "https://wrong-country.test"])
    content = io.BytesIO()
    workbook.save(content)
    mapping = {"level": "Nivel", "utel_url": "URL", "form_type": "Location", "country": "Locale", "inconcert_url": "CRM"}
    app = create_app(
        Settings(
            database_path=tmp_path / "test.db",
            storage_dir=tmp_path / "storage",
            batch_delay_seconds=0,
        )
    )
    with TestClient(app) as client:
        response = client.post('/api/bots/utel-inconcert/batch-run',
                               data={"config": json.dumps({"lead": {}, "dry_run": True, "inconcert_url": "https://stale.test"}), "mapping": json.dumps(mapping)},
                               files={"file": ("test.xlsx", content.getvalue())})
        assert response.status_code == 202, response.text
        job = client.get(f'/api/bots/utel-inconcert/batch/{response.json()["job_id"]}').json()
        assert job["status"] == "PASS", job
    assert seen == [(country, f"https://{tenant}.inconcertcc.com/login?redirect=%2Fmas%2Fhome") for country, tenant in countries]
