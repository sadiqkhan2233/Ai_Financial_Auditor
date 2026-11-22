import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st

from models.database import init_db
from ui.ai_agents import show_ai_agents
from ui.company_page import show_company_management
from ui.dashboard import show_dashboard
from ui.engagement_page import show_engagements
from ui.financial_analysis import show_financial_analysis
from ui.findings_page import show_findings_page
from ui.identity import show_identity_sidebar
from ui.internal_control import show_internal_control
from ui.reports_page import show_reports_page
from ui.risk_dashboard import show_risk_dashboard
from ui.settings_page import show_settings
from ui.transaction_testing import show_transaction_testing
from ui.upload_center import show_upload_center

st.set_page_config(page_title="FinAudit AI", page_icon="📊", layout="wide")

PAGES = [
    "Dashboard", "Company Management", "Audit Engagements", "Document Upload Center",
    "Financial Analysis", "Transaction Testing", "Internal Control Assessment",
    "Audit Risk Dashboard", "AI Audit Assistant", "Audit Findings", "Reports & Downloads", "Settings",
]


@st.cache_resource
def setup_database(version: str = "phase7b"):
    init_db()
    return True


setup_database("phase7b")
st.sidebar.title("FinAudit AI")
page = st.sidebar.radio("Navigation", PAGES)
st.sidebar.caption("Audit support tool. It does not replace a qualified auditor.")
show_identity_sidebar()

ROUTES = {
    "Dashboard": show_dashboard,
    "Company Management": show_company_management,
    "Audit Engagements": show_engagements,
    "Document Upload Center": show_upload_center,
    "Financial Analysis": show_financial_analysis,
    "Transaction Testing": show_transaction_testing,
    "Internal Control Assessment": show_internal_control,
    "Audit Risk Dashboard": show_risk_dashboard,
    "AI Audit Assistant": show_ai_agents,
    "Audit Findings": show_findings_page,
    "Reports & Downloads": show_reports_page,
    "Settings": show_settings,
}
ROUTES[page]()
