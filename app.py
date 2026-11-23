import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st

from config.settings import BASE_DIR
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
from ui.theme import apply_theme
from ui.transaction_testing import show_transaction_testing
from ui.upload_center import show_upload_center

st.set_page_config(page_title="FinAudit AI", page_icon="📊", layout="wide")


@st.cache_resource
def setup_database(version: str = "ui1"):
    init_db()
    return True


def _page(function, title, icon, default=False):
    return st.Page(function, title=title, icon=f":material/{icon}:", default=default)


setup_database("ui1")
apply_theme()

logo = BASE_DIR / "assets" / "logo.svg"
if logo.exists():
    st.logo(str(logo), size="large")

navigation = st.navigation({
    "Overview": [
        _page(show_dashboard, "Dashboard", "dashboard", default=True),
    ],
    "Set up": [
        _page(show_company_management, "Company Management", "apartment"),
        _page(show_engagements, "Audit Engagements", "folder_open"),
        _page(show_upload_center, "Document Upload Center", "upload_file"),
    ],
    "Analysis": [
        _page(show_financial_analysis, "Financial Analysis", "monitoring"),
        _page(show_transaction_testing, "Transaction Testing", "manage_search"),
        _page(show_internal_control, "Internal Control Assessment", "shield"),
        _page(show_risk_dashboard, "Audit Risk Dashboard", "warning"),
        _page(show_ai_agents, "AI Audit Assistant", "smart_toy"),
    ],
    "Review and reporting": [
        _page(show_findings_page, "Audit Findings", "fact_check"),
        _page(show_reports_page, "Reports & Downloads", "description"),
    ],
    "Administration": [
        _page(show_settings, "Settings", "settings"),
    ],
})

show_identity_sidebar()
st.sidebar.caption("Audit support tool. It does not replace a qualified auditor.")
navigation.run()
