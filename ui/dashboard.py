import plotly.express as px
import streamlit as st

from config.settings import get_settings
from models.database import (
    AuditLog, Company, Document, Engagement, Finding, get_session, log_activity,
)
from services.data_access import list_engagements
from services.engagement_summary import summarize_engagement
from services.llm_service import LLMError, LLMService
from services.ratio_engine import calculate_ratios, format_value, monthly_trend
from ui.agent_state import current_answers
from ui.common import pick_engagement

LEVEL_ICONS = {"Low": "🟢", "Medium": "🟡", "High": "🔴", "Not assessed": "⚪"}
SEVERITY_COLORS = {"High": "#c62828", "Medium": "#f9a825", "Low": "#1565c0"}


def _money(value) -> str:
    return f"PKR {value:,.0f}"


def show_dashboard():
    st.title("📊 FinAudit AI")
    st.caption("AI-assisted financial audit support. Every result needs review by a qualified auditor.")
    settings = get_settings()

    with get_session() as session:
        counts = (
            session.query(Company).count(), session.query(Engagement).count(),
            session.query(Document).count(),
            session.query(Finding).filter(Finding.review_status == "Pending Review").count(),
        )
    cols = st.columns(5)
    cols[0].metric("Companies", counts[0])
    cols[1].metric("Engagements", counts[1])
    cols[2].metric("Documents", counts[2])
    cols[3].metric("Findings to review", counts[3])
    cols[4].metric("Groq API key", "Found ✅" if settings.groq_api_key else "Missing ❌")

    if list_engagements():
        st.subheader("Engagement snapshot")
        engagement_id = pick_engagement()
        summary = summarize_engagement(engagement_id, current_answers(engagement_id))
        statements, exceptions, risk = summary["statements"], summary["exceptions"], summary["risk"]

        snap = st.columns(5)
        snap[0].metric("Revenue", _money(statements["revenue"]) if statements else "n/a")
        snap[1].metric("Net profit", _money(statements["net_profit"]) if statements else "n/a")
        ratios = {r["name"]: r for r in calculate_ratios(statements)} if statements else {}
        current = ratios.get("Current Ratio")
        snap[2].metric("Current ratio", format_value(current["value"], current["kind"]) if current else "n/a")
        snap[3].metric("Exceptions", len(exceptions) if exceptions is not None else "n/a")
        score = f" ({risk['overall_score']:.0f}/100)" if risk["overall_score"] is not None else ""
        snap[4].metric("Overall risk", f"{LEVEL_ICONS[risk['overall_level']]} {risk['overall_level']}{score}")

        left, right = st.columns(2)
        with left:
            if not summary["ledger"].empty:
                trend = monthly_trend(summary["ledger"])
                if not trend.empty:
                    st.plotly_chart(px.bar(trend, x="month", y=["Revenue", "Expense"], barmode="group",
                                           title="Monthly revenue and expenses"))
        with right:
            if exceptions:
                data = [{"Severity": s, "Exceptions": sum(1 for e in exceptions if e.severity == s)}
                        for s in ("High", "Medium", "Low")]
                st.plotly_chart(px.bar(data, x="Severity", y="Exceptions", color="Severity",
                                       color_discrete_map=SEVERITY_COLORS, title="Exceptions by severity"))
        st.caption("See the Audit Risk Dashboard page for how the risk level is worked out.")
    else:
        st.info("No engagement yet. Go to the Document Upload Center to upload a file or use the built-in sample.")

    with st.expander("System check"):
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
