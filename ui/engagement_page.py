from datetime import date

import streamlit as st

from services.company_service import list_companies
from services.engagement_manager import (
    STATUSES, create_engagement, delete_engagement, list_engagements_detailed, update_engagement,
)
from ui.flash import flash, show_flash
from ui.identity import get_identity


def show_engagements():
    st.title("📂 Audit Engagements")
    show_flash()
    username, role = get_identity()
    companies = list_companies()
    rows = list_engagements_detailed()

    if rows:
        st.dataframe([
            {"ID": r["id"], "Company": r["company"], "Engagement": r["title"], "Status": r["status"],
             "From": r["period_start"], "To": r["period_end"], "Documents": r["documents"],
             "Findings": r["findings"], "Awaiting review": r["pending"]} for r in rows
        ], hide_index=True)

    with st.expander("Create an engagement", expanded=not rows):
        if not companies:
            st.info("Add a company first on the Company Management page.")
        else:
            by_id = {c["id"]: c["name"] for c in companies}
            with st.form("create_engagement"):
                company_id = st.selectbox("Company", list(by_id), format_func=lambda i: by_id[i])
                title = st.text_input("Engagement title", value="Audit FY 2025-26")
                c1, c2 = st.columns(2)
                start = c1.date_input("Period start", value=date(2025, 7, 1))
                end = c2.date_input("Period end", value=date(2026, 6, 30))
                submitted = st.form_submit_button("Create engagement", type="primary")
            if submitted:
                try:
                    create_engagement(company_id, title, start, end, username=username or "Unknown")
                    flash(f"Engagement '{title.strip()}' was created.")
                    st.rerun()
                except ValueError as err:
                    st.error(str(err))
            st.caption("Tip: when you upload files, typing the same company name and engagement title "
                       "attaches them to the engagement you created here.")

    if not rows:
        return
    st.subheader("Edit or delete")
    by_id = {r["id"]: r for r in rows}
    engagement_id = st.selectbox("Engagement", list(by_id),
                                 format_func=lambda i: f"{by_id[i]['company']} | {by_id[i]['title']}")
    row = by_id[engagement_id]

    with st.form(f"edit_engagement_{engagement_id}"):
        title = st.text_input("Title", value=row["title"])
        status = st.selectbox("Status", STATUSES, index=STATUSES.index(row["status"]))
        c1, c2 = st.columns(2)
        start = c1.date_input("Period start", value=row["period_start"] or date(2025, 7, 1))
        end = c2.date_input("Period end", value=row["period_end"] or date(2026, 6, 30))
        saved = st.form_submit_button("Save changes")
    if saved:
        try:
            update_engagement(engagement_id, title, status, start, end, username=username or "Unknown")
            flash("Engagement updated.")
            st.rerun()
        except ValueError as err:
            st.error(str(err))

    st.markdown("**Delete this engagement**")
    if role != "Admin":
        st.caption("Only an Admin can delete an engagement (change your role in the sidebar).")
        return
    st.warning("This permanently deletes the trial balance, ledger, findings, reports and AI results of this "
               "engagement. The activity log is kept.")
    confirm = st.text_input("Type DELETE to confirm", key=f"confirm_delete_{engagement_id}")
    if st.button("Delete engagement", key=f"delete_engagement_{engagement_id}", disabled=confirm != "DELETE"):
        try:
            removed = delete_engagement(engagement_id, role, username=username or "Unknown")
            flash("Engagement deleted. Removed: " + ", ".join(f"{n} {label}" for label, n in removed.items()))
            st.rerun()
        except (ValueError, PermissionError) as err:
            st.error(str(err))
