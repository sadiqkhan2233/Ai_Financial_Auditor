from datetime import date

import pandas as pd
import streamlit as st

from services.audit_trail import distinct_actions, distinct_users, query_logs
from services.excel_report import build_excel
from services.pdf_report import build_pdf
from services.report_service import (
    REQUIRE_DIFFERENT_APPROVER, build_snapshot, decide_report, get_report, list_reports,
    release_gates, submit_report,
)
from services.user_service import can_finalize
from ui.agent_state import current_answers
from ui.common import pick_engagement
from ui.flash import flash, show_flash
from ui.identity import get_identity

GATE_ICONS = {"pass": "✅", "warn": "⚠️", "block": "❌"}
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _prepare_tab(engagement_id, username):
    answers = current_answers(engagement_id)
    gates = release_gates(engagement_id, answers)
    st.subheader("Release checks")
    for gate in gates:
        st.write(f"{GATE_ICONS[gate['status']]} **{gate['name']}**: {gate['detail']}")
    blocked = any(g["status"] == "block" for g in gates)
    if blocked:
        st.error("Fix the ❌ items before the report can be submitted for approval. A draft preview is always possible.")

    st.subheader("Draft preview")
    st.caption("A preview is watermarked DRAFT PREVIEW and is not saved. Use it to check the layout and content.")
    previews = st.session_state.setdefault("report_previews", {})
    if st.button("Prepare draft files", key=f"prep_{engagement_id}"):
        with st.spinner("Building the PDF and Excel files..."):
            try:
                snap = build_snapshot(engagement_id, answers, prepared_by=username)
                info = {"status": "Draft preview"}
                previews[engagement_id] = {"pdf": build_pdf(snap, info), "xlsx": build_excel(snap, info)}
            except Exception as err:
                st.error(f"Could not build the files: {err}")
    preview = previews.get(engagement_id)
    if preview:
        c1, c2 = st.columns(2)
        c1.download_button("⬇ Draft PDF", preview["pdf"], file_name="audit_report_draft_preview.pdf",
                           mime="application/pdf", key=f"dl_pdf_prev_{engagement_id}")
        c2.download_button("⬇ Draft Excel", preview["xlsx"], file_name="audit_report_draft_preview.xlsx",
                           mime=XLSX_MIME, key=f"dl_xlsx_prev_{engagement_id}")

    st.subheader("Submit for approval")
    st.write("Submitting saves a frozen copy of today's figures and findings. A Reviewer or Admin must then "
             "approve it" + (", and it must be a different person from you." if REQUIRE_DIFFERENT_APPROVER else "."))
    if not username:
        st.warning("Enter your name in the sidebar (Who is working?) first.")
    if st.button("Submit report for approval", type="primary", disabled=blocked or not username,
                 key=f"submit_{engagement_id}"):
        try:
            report_id = submit_report(engagement_id, answers, username)
            flash(f"Report #{report_id} was submitted and is waiting for approval (see tab 2).")
            st.rerun()
        except ValueError as err:
            st.error(str(err))


def _status_info(report):
    return {"status": report["status"], "approved_by": report["approved_by"], "decided_by": report["decided_by"],
            "decided_at": report["decided_at"], "comment": report["decision_comment"]}


def _reports_tab(engagement_id, username, role):
    reports = list_reports(engagement_id)
    if not reports:
        st.info("No report has been submitted yet. Use tab 1.")
        return
    st.dataframe([
        {"Version": r["version"], "Status": r["status"], "Prepared by": r["prepared_by"], "Created": r["created_at"],
         "Decided by": r["decided_by"], "Decided": r["decided_at"]} for r in reports
    ], hide_index=True)

    by_id = {r["id"]: r for r in reports}
    report_id = st.selectbox("Report", list(by_id),
                             format_func=lambda i: f"Version {by_id[i]['version']} - {by_id[i]['status']}")
    report = get_report(report_id)
    status = report["status"]
    if status == "Approved":
        st.success(f"Approved by {report['approved_by']} on {report['decided_at']}. {report['decision_comment']}")
    elif status == "Rejected":
        st.error(f"Rejected by {report['decided_by']} on {report['decided_at']}. Reason: {report['decision_comment']}")
    else:
        st.warning("Waiting for approval. The files below are watermarked until the report is approved.")

    info = _status_info(report)
    c1, c2 = st.columns(2)
    c1.download_button("⬇ PDF report", build_pdf(report["snapshot"], info), mime="application/pdf",
                       file_name=f"audit_report_v{report['version']}_{status.lower().replace(' ', '_')}.pdf",
                       key=f"dl_pdf_{report_id}")
    c2.download_button("⬇ Excel workbook", build_excel(report["snapshot"], info), mime=XLSX_MIME,
                       file_name=f"audit_report_v{report['version']}_{status.lower().replace(' ', '_')}.xlsx",
                       key=f"dl_xlsx_{report_id}")

    if status != "Pending Approval":
        return
    st.subheader("Decision")
    if not can_finalize(role):
        st.info("Only a Reviewer or Admin can approve or reject. Change your role in the sidebar.")
        return
    if not username:
        st.warning("Enter your name in the sidebar first.")
        return
    if REQUIRE_DIFFERENT_APPROVER and username.strip().lower() == report["prepared_by"].strip().lower():
        st.info(f"This report was prepared by {report['prepared_by']}. A different person must approve it. "
                "(To test alone, change your name in the sidebar.)")
    blockers = [g for g in release_gates(engagement_id) if g["status"] == "block"]
    for gate in blockers:
        st.error(gate["detail"])
    comment = st.text_area("Comment (required if you reject)", key=f"comment_{report_id}")
    left, right = st.columns(2)
    if left.button("✅ Approve report", disabled=bool(blockers), key=f"approve_{report_id}"):
        try:
            decide_report(report_id, True, username, role, comment)
            flash("The report was approved. The PDF and Excel files no longer carry a watermark.")
            st.rerun()
        except (ValueError, PermissionError) as err:
            st.error(str(err))
    if right.button("↩️ Reject report", key=f"reject_{report_id}"):
        try:
            decide_report(report_id, False, username, role, comment)
            flash("The report was rejected. Fix the issues and submit a new version.", "warning")
            st.rerun()
        except (ValueError, PermissionError) as err:
            st.error(str(err))


def show_audit_trail():
    st.caption("Every important action is recorded here with the name that was entered. Times are in Pakistan "
               "time (UTC+5). The app has no button to delete log entries.")
    c1, c2, c3 = st.columns(3)
    user = c1.selectbox("User", ["All"] + distinct_users())
    action = c2.selectbox("Action", ["All"] + distinct_actions())
    text = c3.text_input("Search")
    since = until = None
    if st.checkbox("Filter by date"):
        d1, d2 = st.columns(2)
        since = d1.date_input("From", value=date.today())
        until = d2.date_input("To", value=date.today())
    rows = query_logs("" if user == "All" else user, "" if action == "All" else action, text, since, until)
    if not rows:
        st.info("No log entries match.")
        return
    st.write(f"{len(rows)} entr{'y' if len(rows) == 1 else 'ies'} (newest first, up to 2,000).")
    st.dataframe(rows, hide_index=True)
    st.download_button("Download audit trail (CSV)", pd.DataFrame(rows).to_csv(index=False).encode("utf-8"),
                       file_name="audit_trail.csv", mime="text/csv")


def show_reports_page():
    st.title("📄 Reports & Downloads")
    show_flash()
    username, role = get_identity()
    engagement_id = pick_engagement()

    tab_prepare, tab_reports, tab_trail = st.tabs(
        ["1. Prepare and submit", "2. Reports and approval", "3. Audit trail"]
    )
    with tab_prepare:
        if engagement_id is None:
            st.info("Choose or create an engagement first.")
        else:
            _prepare_tab(engagement_id, username)
    with tab_reports:
        if engagement_id is None:
            st.info("Choose or create an engagement first.")
        else:
            _reports_tab(engagement_id, username, role)
    with tab_trail:
        show_audit_trail()
