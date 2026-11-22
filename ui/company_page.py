import streamlit as st

from services.company_service import create_company, delete_company, list_companies, update_company
from ui.flash import flash, show_flash
from ui.identity import get_identity


def show_company_management():
    st.title("🏢 Company Management")
    show_flash()
    username, role = get_identity()
    companies = list_companies()

    if companies:
        st.dataframe([
            {"Company": c["name"], "NTN": c["ntn"], "Industry": c["industry"], "City": c["city"],
             "Engagements": c["engagements"]} for c in companies
        ], hide_index=True)

    with st.expander("Add a company", expanded=not companies):
        with st.form("add_company", clear_on_submit=True):
            c1, c2 = st.columns(2)
            name = c1.text_input("Company name")
            ntn = c2.text_input("NTN (optional)")
            industry = c1.text_input("Industry (optional)")
            city = c2.text_input("City (optional)")
            submitted = st.form_submit_button("Add company", type="primary")
        if submitted:
            try:
                create_company(name, ntn, industry, city, username=username or "Unknown")
                flash(f"Company '{name.strip()}' was added.")
                st.rerun()
            except ValueError as err:
                st.error(str(err))

    if not companies:
        return
    st.subheader("Edit or delete")
    by_id = {c["id"]: c for c in companies}
    company_id = st.selectbox("Company", list(by_id), format_func=lambda i: by_id[i]["name"])
    company = by_id[company_id]

    with st.form(f"edit_company_{company_id}"):
        c1, c2 = st.columns(2)
        name = c1.text_input("Company name", value=company["name"])
        ntn = c2.text_input("NTN", value=company["ntn"])
        industry = c1.text_input("Industry", value=company["industry"])
        city = c2.text_input("City", value=company["city"])
        saved = st.form_submit_button("Save changes")
    if saved:
        try:
            update_company(company_id, name, ntn, industry, city, username=username or "Unknown")
            flash("Company updated.")
            st.rerun()
        except ValueError as err:
            st.error(str(err))

    st.markdown("**Delete this company**")
    if role != "Admin":
        st.caption("Only an Admin can delete a company (change your role in the sidebar).")
    elif company["engagements"]:
        st.caption("This company still has engagements. Delete those first on the Audit Engagements page.")
    elif st.button("Delete company", key=f"del_company_{company_id}"):
        try:
            delete_company(company_id, role, username=username or "Unknown")
            flash("Company deleted.")
            st.rerun()
        except (ValueError, PermissionError) as err:
            st.error(str(err))
