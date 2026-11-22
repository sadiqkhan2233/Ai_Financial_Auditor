from datetime import date
from io import BytesIO

import pytest
from openpyxl import load_workbook

from models.database import init_db, log_activity
from services.audit_trail import query_logs
from services.backup_service import create_backup, inspect_backup_bytes, restore_backup
from services.company_service import create_company, list_companies
from services.data_access import load_transactions
from services.excel_report import build_excel
from services.findings_service import list_findings, save_exceptions, update_review
from services.pdf_report import build_pdf
from services.report_service import (
    build_snapshot, decide_report, get_report, list_reports, release_gates, submit_report,
)
from services.sample_loader import load_sample_data
from services.transaction_checks import run_all_tests


def _ready(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'p7b.db'}")
    init_db()
    try:
        return load_sample_data()
    except FileNotFoundError:
        pytest.skip("Sample files not added yet")


def _decide_high_findings(engagement_id):
    save_exceptions(engagement_id, run_all_tests(load_transactions(engagement_id)))
    for finding in list_findings(engagement_id):
        if finding["severity"] == "High":
            update_review(finding["id"], "Confirmed Issue", "Sara", "Reviewer", "Checked against the invoices")


def _blocks(engagement_id):
    return [g for g in release_gates(engagement_id) if g["status"] == "block"]


def test_release_gates_follow_the_review_rules(tmp_path, monkeypatch):
    engagement_id = _ready(tmp_path, monkeypatch)
    assert any("not saved" in g["detail"] for g in _blocks(engagement_id))
    save_exceptions(engagement_id, run_all_tests(load_transactions(engagement_id)))
    assert any("high-severity" in g["detail"] for g in _blocks(engagement_id))
    _decide_high_findings(engagement_id)
    assert _blocks(engagement_id) == []


def test_report_files_are_built(tmp_path, monkeypatch):
    engagement_id = _ready(tmp_path, monkeypatch)
    _decide_high_findings(engagement_id)
    snap = build_snapshot(engagement_id, None, prepared_by="Ali")
    pdf = build_pdf(snap, {"status": "Draft preview"})
    assert pdf.startswith(b"%PDF") and len(pdf) > 3000
    workbook = load_workbook(BytesIO(build_excel(snap, {"status": "Draft preview"})))
    assert {"Summary", "Trial Balance", "Ratios", "Findings"} <= set(workbook.sheetnames)
    assert workbook["Findings"].max_row == len(snap["findings"]) + 1


def test_approval_workflow(tmp_path, monkeypatch):
    engagement_id = _ready(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        submit_report(engagement_id, None, "Ali")  # exceptions not saved yet
    _decide_high_findings(engagement_id)
    with pytest.raises(ValueError):
        submit_report(engagement_id, None, "")  # a name is required
    report_id = submit_report(engagement_id, None, "Ali")
    with pytest.raises(ValueError):
        submit_report(engagement_id, None, "Ali")  # one report is already waiting

    with pytest.raises(PermissionError):
        decide_report(report_id, True, "Sara", "Auditor", "")
    with pytest.raises(PermissionError):
        decide_report(report_id, True, "ali", "Reviewer", "")  # the preparer cannot approve
    with pytest.raises(ValueError):
        decide_report(report_id, False, "Sara", "Reviewer", "no")  # reason too short

    decide_report(report_id, True, "Sara", "Reviewer", "Looks right")
    report = get_report(report_id)
    assert report["status"] == "Approved" and report["approved_by"] == "Sara"
    assert list_reports(engagement_id)[0]["status"] == "Approved"
    with pytest.raises(ValueError):
        decide_report(report_id, True, "Sara", "Reviewer", "")  # already decided
    assert build_pdf(report["snapshot"], {"status": "Approved", "approved_by": "Sara"}).startswith(b"%PDF")


def test_audit_trail_filters(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'trail.db'}")
    init_db()
    log_activity("thing_a", "first detail", username="Ali")
    log_activity("thing_b", "second detail", username="Sara")
    assert len(query_logs()) == 2
    assert [r["User"] for r in query_logs(user="Sara")] == ["Sara"]
    assert [r["Action"] for r in query_logs(action="thing_a")] == ["thing_a"]
    assert len(query_logs(text="second")) == 1
    assert len(query_logs(since=date.today(), until=date.today())) == 2


def test_backup_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'backup.db'}")
    init_db()
    create_company("Keep Co")
    data = create_backup()
    create_company("Temporary Co")
    assert len(list_companies()) == 2
    summary = restore_backup(data, "Admin Ali")
    assert [c["name"] for c in list_companies()] == ["Keep Co"]
    assert summary["companies"] == 1


def test_bad_backup_files_are_rejected():
    with pytest.raises(ValueError):
        inspect_backup_bytes(b"this is not a database")
