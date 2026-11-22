import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st

from config.settings import get_settings
from models.database import init_db
from ui.ai_agents import show_ai_agents
from ui.company_page import show_company_management
from ui.dashboard import show_dashboard
from ui.engagement_page import show_engagements
from ui.financial_analysis import show_financial_analysis
from ui.findings_page import show_findings_page
from ui.identity import show_identity_sidebar
from ui.internal_control import show_internal_control
from ui.risk_dashboard import show_risk_dashboard
from ui.transaction_testing import show_transaction_testing
from ui.upload_center import show_upload_center

st.set_page_config(page_title="FinAudit AI", page_icon="📊", layout="wide")

PAGES = [
    "Dashboard", "Company Management", "Audit Engagements", "Document Upload Center",
    "Financial Analysis", "Transaction Testing", "Internal Control Assessment",
    "Audit Risk Dashboard", "AI Audit Assistant", "Audit Findings", "Reports & Downloads", "Settings",
]


@st.cache_resource
def setup_database(version: str = "phase7a"):
    init_db()
    return True


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


setup_database("phase7a")
st.sidebar.title("FinAudit AI")
page = st.sidebar.radio("Navigation", PAGES)
st.sidebar.caption("Audit support tool. It does not replace a qualified auditor.")
show_identity_sidebar()

if page == "Dashboard":
    show_dashboard()
elif page == "Company Management":
    show_company_management()
elif page == "Audit Engagements":
    show_engagements()
elif page == "Document Upload Center":
    show_upload_center()
elif page == "Financial Analysis":
    show_financial_analysis()
elif page == "Transaction Testing":
    show_transaction_testing()
elif page == "Internal Control Assessment":
    show_internal_control()
elif page == "Audit Risk Dashboard":
    show_risk_dashboard()
elif page == "AI Audit Assistant":
    show_ai_agents()
elif page == "Audit Findings":
    show_findings_page()
elif page == "Settings":
    show_settings()
else:
    st.title(page)
    st.info("This page will be built in **Phase 7, part B** (PDF and Excel reports with approval).")
