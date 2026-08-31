from datetime import date

from backend.app.services.test_lead_service import TestLeadService


def test_reserves_unique_country_aware_test_leads(tmp_path):
    service = TestLeadService(tmp_path / "leads.db")

    first = service.reserve("México")
    second = service.reserve("México")
    third = service.reserve("Colombia")

    assert first["email"] == f"Testing{date.today().isoformat()}N1@testingUtel.com"
    assert second["email"].endswith("N2@testingUtel.com")
    assert len(first["phone"]) == 10
    assert first["phone"].startswith("55")
    assert len(third["phone"]) == 10
    assert third["phone"].startswith("3")
    assert len({first["email"], second["email"], third["email"]}) == 3
    assert len({first["phone"], second["phone"], third["phone"]}) == 3
