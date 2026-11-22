"""Report snapshots, release checks and the approval workflow."""
import json
from datetime import datetime, timezone

from flows.checkpoints import run_data_checkpoint
from models.database import Company, Document, Engagement, Report, get_session, log_activity, utcnow
from services.account_classifier import classify_trial_balance
from services.control_questionnaire import any_answered
from services.data_access import load_transactions, load_trial_balance
from services.engagement_summary import summarize_engagement
from services.findings_service import FINAL_STATUSES, findings_summary, list_findings
from services.ratio_engine import calculate_ratios, format_value, review_points
from services.results_store import load_agent_results
from services.transaction_checks import run_all_tests
from services.user_service import can_finalize

# Set this to False if you are testing alone and want to approve your own report.
REQUIRE_DIFFERENT_APPROVER = True


def release_gates(engagement_id: int, control_answers: dict | None = None) -> list:
    """Checks that must pass before a report can be submitted or approved."""
    gates = []

    def add(name, status, detail):
        gates.append({"name": name, "status": status, "detail": detail})

    tb = load_trial_balance(engagement_id)
    ledger = load_transactions(engagement_id)
    findings = list_findings(engagement_id)

    if tb.empty:
        add("Trial balance saved", "block", "No trial balance is saved for this engagement.")
    else:
        checkpoint = run_data_checkpoint(engagement_id)
        failed = [c["detail"] for c in checkpoint["checks"] if c["status"] == "fail"]
        if failed:
            add("Data checks", "block", "; ".join(failed))
        else:
            add("Data checks", "pass", "The data checks passed.")

    if not ledger.empty:
        exceptions = run_all_tests(ledger)
        saved = {(f["title"], f["transaction_refs"]) for f in findings}
        unsaved = [e for e in exceptions if (e.title[:200], e.references) not in saved]
        if unsaved:
            add("Exceptions reviewed", "block",
                f"{len(unsaved)} exception(s) found by the tests are not saved as findings. "
                "Save them on the Transaction Testing page so a person reviews them.")
        else:
            add("Exceptions reviewed", "pass", "Every exception is saved as a finding.")

    high_open = [f for f in findings if f["severity"] == "High" and f["review_status"] not in FINAL_STATUSES]
    if high_open:
        add("High-severity findings decided", "block",
            f"{len(high_open)} high-severity finding(s) still need a final decision on the Audit Findings page.")
    else:
        add("High-severity findings decided", "pass", "All high-severity findings have a final decision.")

    other_open = [f for f in findings if f["severity"] != "High" and f["review_status"] == "Pending Review"]
    if other_open:
        add("Other findings", "warn", f"{len(other_open)} medium or low finding(s) are still pending review. "
                                      "They will be shown as pending in the report.")

    ai = load_agent_results(engagement_id)
    if "reporting" not in ai:
        add("AI draft", "warn", "No AI draft report was saved, so the report uses figures and findings only.")
    if "qa" in ai and ai["qa"].get("status") != "Pass":
        add("AI quality review", "warn", "The AI quality review said 'Needs review'. A reviewer should read it.")
    if control_answers is not None and not any_answered(control_answers):
        add("Internal controls", "warn", "The control questionnaire has not been answered.")
    return gates


def build_snapshot(engagement_id: int, control_answers: dict | None = None,
                   prepared_by: str = "", version: int | None = None) -> dict:
    """Collects everything the report needs into one plain dictionary (saved when a report is submitted)."""
    with get_session() as session:
        engagement = session.get(Engagement, engagement_id)
        if engagement is None:
            raise ValueError("That engagement no longer exists.")
        company = session.get(Company, engagement.company_id)
        meta = {
            "company": company.name if company else "", "engagement": engagement.title,
            "period_start": engagement.period_start.isoformat() if engagement.period_start else "",
            "period_end": engagement.period_end.isoformat() if engagement.period_end else "",
            "engagement_status": engagement.status, "prepared_by": prepared_by, "version": version,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        documents = [
            {"filename": d.filename, "type": d.file_type, "status": d.status,
             "uploaded": d.uploaded_at.strftime("%Y-%m-%d")}
            for d in session.query(Document).filter_by(engagement_id=engagement_id).order_by(Document.id).all()
        ]

    summary = summarize_engagement(engagement_id, control_answers)
    tb, ledger, statements = summary["tb"], summary["ledger"], summary["statements"]

    trial_balance = []
    if not tb.empty:
        classified = classify_trial_balance(tb)
        trial_balance = [
            {"code": r.account_code, "name": r.account_name, "category": r.category,
             "debit": float(r.debit), "credit": float(r.credit)}
            for r in classified.itertuples()
        ]
    dates = ledger["date"].dropna() if not ledger.empty else []
    ai = load_agent_results(engagement_id)

    return {
        "meta": meta,
        "documents": documents,
        "data": {
            "tb_accounts": len(tb), "ledger_lines": len(ledger),
            "ledger_from": dates.min().strftime("%d %b %Y") if len(dates) else "",
            "ledger_to": dates.max().strftime("%d %b %Y") if len(dates) else "",
        },
        "checks": summary["checkpoint"]["checks"] if summary["checkpoint"] else [],
        "statements": statements,
        "trial_balance": trial_balance,
        "ratios": [
            {**r, "text": format_value(r["value"], r["kind"])} for r in calculate_ratios(statements)
        ] if statements else [],
        "review_points": review_points(statements) if statements else [],
        "risk": summary["risk"],
        "controls": summary["controls"] or [],
        "findings": list_findings(engagement_id),
        "findings_summary": findings_summary(engagement_id),
        "ai": {
            "draft": ai["reporting"]["output"] if "reporting" in ai else None,
            "draft_saved_at": ai["reporting"].get("saved_at", "") if "reporting" in ai else "",
            "qa_status": ai["qa"].get("status") if "qa" in ai else None,
        },
    }


def _row(r: Report) -> dict:
    return {
        "id": r.id, "engagement_id": r.engagement_id, "version": r.version or 1, "title": r.title,
        "status": r.status, "prepared_by": r.prepared_by or "", "approved_by": r.approved_by or "",
        "decided_by": r.decided_by or "", "decision_comment": r.decision_comment or "",
        "decided_at": r.decided_at.strftime("%Y-%m-%d %H:%M") if r.decided_at else "",
        "created_at": r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "",
    }


def list_reports(engagement_id: int) -> list:
    with get_session() as session:
        rows = session.query(Report).filter_by(engagement_id=engagement_id).order_by(Report.id.desc()).all()
        return [_row(r) for r in rows]


def get_report(report_id: int) -> dict | None:
    with get_session() as session:
        report = session.get(Report, report_id)
        if report is None:
            return None
        data = _row(report)
        data["snapshot"] = json.loads(report.snapshot_json) if report.snapshot_json else {}
        return data


def submit_report(engagement_id: int, control_answers: dict | None, username: str) -> int:
    username = (username or "").strip()
    if not username:
        raise ValueError("Enter your name in the sidebar first, so the report shows who prepared it.")
    blockers = [g["detail"] for g in release_gates(engagement_id, control_answers) if g["status"] == "block"]
    if blockers:
        raise ValueError("The report cannot be submitted yet: " + " ".join(blockers))

    with get_session() as session:
        existing = session.query(Report).filter_by(engagement_id=engagement_id).all()
        if any(r.status == "Pending Approval" for r in existing):
            raise ValueError("A report is already waiting for approval. Approve or reject it first.")
        version = max([r.version or 1 for r in existing], default=0) + 1

    snapshot = build_snapshot(engagement_id, control_answers, prepared_by=username, version=version)
    title = f"Audit Support Report v{version} - {snapshot['meta']['company']} - {snapshot['meta']['engagement']}"
    with get_session() as session:
        report = Report(engagement_id=engagement_id, title=title[:200], status="Pending Approval",
                        version=version, prepared_by=username,
                        snapshot_json=json.dumps(snapshot, default=str))
        session.add(report)
        session.flush()
        report_id = report.id
        session.commit()
    log_activity("report_submitted", f"report {report_id} (v{version}) for engagement {engagement_id}",
                 username=username)
    return report_id


def decide_report(report_id: int, approve: bool, username: str, role: str, comment: str = "") -> None:
    username, comment = (username or "").strip(), (comment or "").strip()
    if not username:
        raise ValueError("Enter your name in the sidebar first.")
    if not can_finalize(role):
        raise PermissionError("Only a Reviewer or Admin can approve or reject a report.")
    if not approve and len(comment) < 5:
        raise ValueError("Please write a short reason for rejecting the report.")

    with get_session() as session:
        report = session.get(Report, report_id)
        if report is None:
            raise ValueError("That report no longer exists.")
        if report.status != "Pending Approval":
            raise ValueError("This report has already been decided.")
        if REQUIRE_DIFFERENT_APPROVER and (report.prepared_by or "").strip().lower() == username.lower():
            raise PermissionError("The person who prepared the report cannot approve or reject it. "
                                  "Ask a second person.")
        engagement_id, version = report.engagement_id, report.version

    if approve:
        blockers = [g["detail"] for g in release_gates(engagement_id) if g["status"] == "block"]
        if blockers:
            raise ValueError("Conditions changed since the report was submitted: " + " ".join(blockers))

    with get_session() as session:
        report = session.get(Report, report_id)
        report.status = "Approved" if approve else "Rejected"
        report.decided_by, report.decided_at = username, utcnow()
        report.decision_comment = comment or None
        if approve:
            report.approved_by = username
        session.commit()
    log_activity("report_approved" if approve else "report_rejected",
                 f"report {report_id} (v{version}); by {username} ({role}); comment: {comment[:200]}",
                 username=username)
