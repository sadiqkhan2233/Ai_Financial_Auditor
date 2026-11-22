import pandas as pd
import streamlit as st

from services.findings_service import (
    AUDITOR_STATUSES, FINAL_STATUSES, SEVERITIES, STATUSES, add_manual_finding, finding_history,
    findings_summary, list_findings, update_review,
)
from services.user_service import can_finalize
from ui.common import pick_engagement
from ui.flash import flash, show_flash
from ui.identity import get_identity

SEVERITY_ICONS = {"High": "🔴", "Medium": "🟡", "Low": "🔵"}
STATUS_ICONS = {"Pending Review": "⏳", "Under Investigation": "🔍", "Confirmed Issue": "❗",
                "Cleared - Explained": "✅", "Dismissed": "🚫"}


def _manual_form(engagement_id, username):
    with st.expander("Add a finding manually"):
        with st.form("manual_finding", clear_on_submit=True):
            title = st.text_input("Title")
            severity = st.selectbox("Severity", SEVERITIES, index=1)
            explanation = st.text_area("What did you notice, and why does it matter?")
            evidence = st.text_area("Evidence (documents, amounts, dates)")
            references = st.text_input("References (voucher or invoice numbers)")
            submitted = st.form_submit_button("Add finding", type="primary")
        if submitted:
            try:
                add_manual_finding(engagement_id, title, severity, explanation, evidence, references,
                                   username=username or "Unknown")
                flash("Finding added with status 'Pending Review'.")
                st.rerun()
            except ValueError as err:
                st.error(str(err))


def _review_section(shown, username, role):
    st.subheader("Review a finding")
    labels = {
        f"#{f['id']}  {STATUS_ICONS[f['review_status']]} {f['title']} [{f['severity']}]": f for f in shown
    }
    finding = labels[st.selectbox("Choose a finding", list(labels))]

    st.write(f"**Severity:** {SEVERITY_ICONS[finding['severity']]} {finding['severity']}   |   "
             f"**Status:** {STATUS_ICONS[finding['review_status']]} {finding['review_status']}")
    if finding["reviewer"]:
        st.caption(f"Last reviewed by {finding['reviewer']} on {finding['reviewed_at']}")
    st.write(f"**Method:** {finding['method']}")
    st.write(f"**Explanation:** {finding['explanation']}")
    st.write(f"**References:** {finding['transaction_refs']}")
    if finding["evidence"]:
        st.text(finding["evidence"])
    if finding["review_comment"]:
        st.info(f"Reviewer comment: {finding['review_comment']}")

    history = finding_history(finding["id"])
    if history:
        with st.expander("Review history"):
            for item in history:
                st.write(f"{item['time']}: {item['details']}")

    current = finding["review_status"]
    options = STATUSES if can_finalize(role) else AUDITOR_STATUSES
    if current in FINAL_STATUSES and not can_finalize(role):
        st.info("This finding has a final status. Only a Reviewer or Admin can change it.")
        return
    if not username:
        st.warning("Enter your name in the sidebar (Who is working?) before saving a review.")
    with st.form(f"review_form_{finding['id']}"):
        status = st.selectbox("Review status", options, index=options.index(current) if current in options else 0)
        comment = st.text_area("Comment (a reason is required for a final decision)",
                               value=finding["review_comment"])
        submitted = st.form_submit_button("Save review", type="primary")
    if not can_finalize(role):
        st.caption("As an Auditor you can mark findings 'Under Investigation'. A Reviewer or Admin makes the "
                   "final decision.")
    if submitted:
        try:
            update_review(finding["id"], status, username, role, comment)
            flash(f"Finding #{finding['id']} is now '{status}'.")
            st.rerun()
        except (ValueError, PermissionError) as err:
            st.error(str(err))


def show_findings_page():
    st.title("📝 Audit Findings")
    st.caption("Every exception needs a human decision. A detected anomaly is something to investigate, "
               "not proof of fraud.")
    show_flash()
    engagement_id = pick_engagement()
    if engagement_id is None:
        return
    username, role = get_identity()

    summary = findings_summary(engagement_id)
    counts = summary["counts"]
    cols = st.columns(5)
    cols[0].metric("Findings", summary["total"])
    cols[1].metric("⏳ Pending", counts["Pending Review"])
    cols[2].metric("🔍 Investigating", counts["Under Investigation"])
    cols[3].metric("❗ Confirmed", counts["Confirmed Issue"])
    cols[4].metric("✅ Cleared or dismissed", counts["Cleared - Explained"] + counts["Dismissed"])
    if summary["high_open"]:
        st.warning(f"{summary['high_open']} high-severity finding(s) still need a final decision. "
                   "They must be decided before a report can be released.")

    findings = list_findings(engagement_id)
    if not findings:
        st.info("No findings yet. Run the tests on the Transaction Testing page and press "
                "'Save exceptions to Audit Findings', or add a finding manually below.")
        _manual_form(engagement_id, username)
        return

    c1, c2, c3 = st.columns(3)
    statuses = c1.multiselect("Status", STATUSES, default=STATUSES)
    severities = c2.multiselect("Severity", SEVERITIES, default=SEVERITIES)
    search = c3.text_input("Search")
    shown = [
        f for f in findings
        if f["review_status"] in statuses and f["severity"] in severities
        and (not search or search.lower() in (f["title"] + f["transaction_refs"] + f["explanation"]).lower())
    ]
    if not shown:
        st.info("No findings match your filters.")
    else:
        table = pd.DataFrame([
            {"ID": f["id"], "Severity": f"{SEVERITY_ICONS[f['severity']]} {f['severity']}",
             "Title": f["title"], "References": f["transaction_refs"],
             "Status": f"{STATUS_ICONS[f['review_status']]} {f['review_status']}", "Reviewer": f["reviewer"]}
            for f in shown
        ])
        st.dataframe(table, hide_index=True)
        st.download_button("Download findings (CSV)", pd.DataFrame(shown).to_csv(index=False).encode("utf-8"),
                           file_name="findings.csv", mime="text/csv")
        _review_section(shown, username, role)
    _manual_form(engagement_id, username)
