from datetime import date

import pytest
from sqlalchemy import text

from models.database import get_engine, init_db
from services.company_service import create_company, delete_company, list_companies
from services.data_access import load_transactions
from services.engagement_manager import create_engagement, delete_engagement
from services.engagement_service import get_or_create_engagement
from services.findings_service import (
    finding_history, findings_summary, get_finding, list_findings, save_exceptions, update_review,
)
from services.results_store import load_agent_results, save_agent_result
from services.sample_loader import load_sample_data
from services.transaction_checks import ExceptionItem


def _db(tmp_path, monkeypatch, name="p7.db"):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / name}")
    init_db()


def _item(severity):
    return ExceptionItem(test="t", severity=severity, title=f"Finding {severity}", references=f"R-{severity}",
                         method="m", explanation="e", evidence="v")


def test_company_rules(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    company_id = create_company("Alpha Ltd", city="Lahore")
    with pytest.raises(ValueError):
        create_company("alpha ltd")
    engagement_id = create_engagement(company_id, "Audit 1", date(2025, 7, 1), date(2026, 6, 30))
    with pytest.raises(ValueError):
        create_engagement(company_id, "Audit 2", date(2026, 6, 30), date(2025, 7, 1))
    with pytest.raises(PermissionError):
        delete_company(company_id, "Auditor")
    with pytest.raises(ValueError):
        delete_company(company_id, "Admin")  # it still has an engagement
    delete_engagement(engagement_id, "Admin")
    delete_company(company_id, "Admin")
    assert list_companies() == []


def test_deleting_an_engagement_removes_its_data(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    try:
        engagement_id = load_sample_data()
    except FileNotFoundError:
        pytest.skip("Sample files not added yet")
    save_exceptions(engagement_id, [_item("High")])
    with pytest.raises(PermissionError):
        delete_engagement(engagement_id, "Auditor")
    removed = delete_engagement(engagement_id, "Admin")
    assert removed["transactions"] > 0 and removed["findings"] == 1
    assert load_transactions(engagement_id).empty


def test_review_rules(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    engagement_id = get_or_create_engagement("Test Co", "Audit 1")
    save_exceptions(engagement_id, [_item("High"), _item("Low")])
    finding_id = list_findings(engagement_id)[0]["id"]

    with pytest.raises(PermissionError):
        update_review(finding_id, "Confirmed Issue", "Ali", "Auditor", "A reason that is long enough")
    update_review(finding_id, "Under Investigation", "Ali", "Auditor", "")
    with pytest.raises(ValueError):
        update_review(finding_id, "Confirmed Issue", "Sara", "Reviewer", "")
    with pytest.raises(ValueError):
        update_review(finding_id, "Under Investigation", "", "Auditor", "")
    assert findings_summary(engagement_id)["high_open"] == 1

    update_review(finding_id, "Confirmed Issue", "Sara", "Reviewer", "Duplicate confirmed by invoice check")
    finding = get_finding(finding_id)
    assert finding["review_status"] == "Confirmed Issue" and finding["reviewer"] == "Sara"
    assert findings_summary(engagement_id)["high_open"] == 0
    assert len(finding_history(finding_id)) == 2
    with pytest.raises(PermissionError):
        update_review(finding_id, "Pending Review", "Ali", "Auditor", "")


def test_agent_results_roundtrip(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    engagement_id = get_or_create_engagement("Test Co", "Audit 1")
    save_agent_result(engagement_id, "data_analyst", {"output": {"summary": "first"}, "seconds": 1.2})
    save_agent_result(engagement_id, "data_analyst", {"output": {"summary": "second"}, "seconds": 2.0})
    loaded = load_agent_results(engagement_id)
    assert loaded["data_analyst"]["output"]["summary"] == "second"
    assert "saved_at" in loaded["data_analyst"]


def test_old_database_gets_new_columns(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'old.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    with get_engine(url).begin() as conn:
        conn.execute(text("CREATE TABLE findings (id INTEGER PRIMARY KEY, engagement_id INTEGER, "
                          "title VARCHAR(200), review_status VARCHAR(30))"))
    init_db()
    with get_engine(url).begin() as conn:
        columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(findings)")}
    assert {"review_comment", "reviewed_at"} <= columns
