import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st

from config.settings import get_settings
from models.database import (
    AuditLog, Company, Engagement, Finding, get_session, init_db, log_activity,
)
from services.llm_service import LLMError, LLMService

st.set_page_config(page_title="FinAudit AI", page_icon="📊", layout="wide")

COMING_LATER = {
    "Company Management": "Phase 7",
    "Audit Engagements": "Phase 7",
    "Document Upload Center": "Phase 2",
    "Financial Analysis": "Phase 3",
    "Transaction Testing": "Phase 3",
    "Internal Control Assessment": "Phase 4",
    "Audit Risk Dashboard": "Phase 6",
    "AI Audit Assistant": "Phase 5",
    "Audit Findings": "Phase 7",
    "Reports & Downloads": "Phase 7",
}
PAGES = ["Dashboard"] + list(COMING_LATER) + ["Settings"]


@st.cache_resource
def setup_database():
    init_db()
    return True


def show_dashboard():
    st.title("📊 FinAudit AI")
    st.caption("AI-assisted financial audit support. Every result needs review by a qualified auditor.")
    settings = get_settings()

    with get_session() as session:
        companies = session.query(Company).count()
        engagements = session.query(Engagement).count()
        findings = session.query(Finding).count()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Companies", companies)
    c2.metric("Engagements", engagements)
    c3.metric("Findings", findings)
    c4.metric("Groq API key", "Found ✅" if settings.groq_api_key else "Missing ❌")

    st.subheader("System check")
    st.write(f"AI model in use: `{settings.groq_model}`")
    if st.button("Test Groq connection"):
        with st.spinner("Contacting Groq..."):
            try:
                reply = LLMService().ask("Reply with the single word: OK")
                st.success(f"Connected. The AI replied: {reply[:60]}")
                log_activity("groq_connection_test", "success")
            except LLMError as err:
                st.error(str(err))
                log_activity("groq_connection_test", f"failed: {err}")

    st.subheader("Recent activity")
    with get_session() as session:
        logs = session.query(AuditLog).order_by(AuditLog.id.desc()).limit(10).all()
    if logs:
        st.table([{"Time": l.timestamp.strftime("%Y-%m-%d %H:%M"), "Action": l.action} for l in logs])
    else:
        st.info("No activity yet.")


def show_settings():
    st.title("⚙️ Settings")
    s = get_settings()
    st.write(f"**AI model:** `{s.groq_model}`")
    st.write(f"**Maximum upload size:** {s.max_upload_mb} MB")
    st.write(f"**API key:** {'Set' if s.groq_api_key else 'Not set'}")
    st.warning(
        "Demo storage notice: this app uses SQLite and temporary file storage. "
        "Data can disappear when the cloud app restarts. This is fine for a portfolio demo "
        "but not for real client data. The design allows a later move to PostgreSQL."
    )
    st.info("To change the model or key, edit them in Streamlit Cloud → App settings → Secrets.")


setup_database()
st.sidebar.title("FinAudit AI")
page = st.sidebar.radio("Navigation", PAGES)
st.sidebar.caption("Audit support tool. It does not replace a qualified auditor.")

if page == "Dashboard":
    show_dashboard()
elif page == "Settings":
    show_settings()
else:
    st.title(page)
    st.info(f"This page will be built in **{COMING_LATER[page]}**.")
