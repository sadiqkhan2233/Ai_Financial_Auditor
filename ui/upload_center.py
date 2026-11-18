import streamlit as st

from config.settings import BASE_DIR
from models.database import log_activity
from services.document_processor import extract_pdf, get_sheet_names, process_table, read_table
from services.document_service import list_documents, save_ledger, save_pdf_document, save_trial_balance
from services.engagement_service import get_or_create_engagement
from services.file_validation import validate_upload

SAMPLE_DIR = BASE_DIR / "data" / "sample_data"
SAMPLE_FILES = {
    "Trial Balance": SAMPLE_DIR / "sample_trial_balance.csv",
    "General Ledger": SAMPLE_DIR / "sample_general_ledger.csv",
}


def show_upload_center():
    st.title("📁 Document Upload Center")
    st.caption("Upload a trial balance or general ledger (CSV or Excel). PDFs are read for text only.")

    doc_type = st.selectbox("What are you uploading?", ["Trial Balance", "General Ledger"])
    source = st.radio("Data source", ["Upload my own file", "Use built-in sample data"], horizontal=True)

    if source == "Upload my own file":
        uploaded = st.file_uploader("Choose a file", type=["csv", "xlsx", "pdf"])
        if uploaded is None:
            st.info("Choose a file to begin, or switch to the built-in sample data.")
            _show_saved_documents()
            return
        filename, data = uploaded.name, uploaded.getvalue()
    else:
        path = SAMPLE_FILES[doc_type]
        if not path.exists():
            st.error(f"Sample file not found: data/sample_data/{path.name}. Please add it on GitHub.")
            return
        filename, data = path.name, path.read_bytes()

    ok, message = validate_upload(filename, data)
    if not ok:
        st.error(message)
        return

    if filename.lower().endswith(".pdf"):
        _handle_pdf(filename, data)
    else:
        _handle_table(filename, data, doc_type)
    _show_saved_documents()


def _engagement_inputs():
    st.subheader("Save to an engagement")
    col1, col2 = st.columns(2)
    company = col1.text_input("Company name", "Demo Traders (Pvt) Ltd")
    title = col2.text_input("Engagement title", "Audit FY 2025-26")
    return company.strip(), title.strip()


def _show_report(report):
    stats = report.stats
    if stats:
        cols = st.columns(4)
        cols[0].metric("Rows", stats.get("rows", 0))
        cols[1].metric("Total debit (PKR)", f"{stats.get('total_debit', 0):,.0f}")
        cols[2].metric("Total credit (PKR)", f"{stats.get('total_credit', 0):,.0f}")
        if "difference" in stats:
            cols[3].metric("Difference", f"{stats['difference']:,.0f}")
    for msg in report.errors:
        st.error(msg)
    for msg in report.warnings:
        st.warning(msg)
    for msg in report.info:
        st.info(msg)
    if report.passed:
        st.success("✅ Validation passed. You can save this data.")


def _handle_table(filename, data, doc_type):
    sheet = None
    if filename.lower().endswith(".xlsx"):
        try:
            sheets = get_sheet_names(data)
        except Exception as err:
            st.error(f"Could not open this Excel file: {err}")
            return
        if len(sheets) > 1:
            sheet = st.selectbox("Which sheet should be used?", sheets)

    try:
        raw = read_table(filename, data, sheet)
    except Exception as err:
        st.error(f"Could not read this file: {err}")
        return

    with st.expander("Preview of the original file"):
        st.dataframe(raw.head(10))

    clean, report = process_table(raw, doc_type)
    _show_report(report)
    if clean.empty:
        return

    st.subheader("Cleaned data")
    st.dataframe(clean)

    if not report.passed:
        st.error("Fix the errors above and upload the file again. Nothing was saved.")
        return

    company, title = _engagement_inputs()
    if st.button("Save to database", type="primary"):
        if not company or not title:
            st.error("Please enter a company name and an engagement title.")
            return
        try:
            engagement_id = get_or_create_engagement(company, title)
            if doc_type == "Trial Balance":
                save_trial_balance(clean, engagement_id, filename)
            else:
                save_ledger(clean, engagement_id, filename)
            log_activity("document_saved", f"{filename} ({doc_type}), {len(clean)} rows, engagement {engagement_id}")
            st.success(f"Saved {len(clean)} rows from {filename}.")
        except Exception as err:
            st.error(f"Could not save the data: {err}")


def _handle_pdf(filename, data):
    try:
        pages, text, tables = extract_pdf(data)
    except Exception as err:
        st.error(f"Could not read this PDF: {err}")
        return

    st.success(f"PDF read: {pages} page(s).")
    if not text.strip():
        st.warning("No text was found. This looks like a scanned image, which is not supported yet. "
                   "Please upload Excel or CSV instead.")
    else:
        st.text_area("Extracted text (first 3,000 characters)", text[:3000], height=250)
    for page_no, table in tables[:3]:
        st.write(f"Table found on page {page_no}")
        st.dataframe(table)
    st.info("PDF content is stored for reference only. For calculations and testing, "
            "upload the figures as Excel or CSV.")

    company, title = _engagement_inputs()
    if st.button("Save PDF record", type="primary"):
        if not company or not title:
            st.error("Please enter a company name and an engagement title.")
            return
        try:
            engagement_id = get_or_create_engagement(company, title)
            save_pdf_document(engagement_id, filename)
            log_activity("document_saved", f"{filename} (PDF), engagement {engagement_id}")
            st.success("PDF record saved.")
        except Exception as err:
            st.error(f"Could not save: {err}")


def _show_saved_documents():
    st.subheader("Saved documents")
    docs = list_documents()
    if docs:
        st.dataframe(docs)
    else:
        st.info("Nothing saved yet.")
