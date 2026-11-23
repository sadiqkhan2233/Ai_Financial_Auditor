from datetime import timedelta

import plotly.express as px
import streamlit as st

from config.settings import get_settings
from models.database import (
    AuditLog, Company, Document, Engagement, Finding, get_session, log_activity,
)
from services.data_access import list_engagements
from services.engagement_summary import summarize_engagement
from services.findings_service import findings_summary
from services.llm_service import LLMError, LLMService
from services.ratio_engine import calculate_ratios, format_value, monthly_trend
from services.report_service import list_reports
from services.results_store import load_agent_results
from ui.agent_state import current_answers
from ui.common import pick_engagement
from ui.theme import hero, stepper

LEVEL_ICONS = {"Low": "🟢", "Medium": "🟡", "High": "🔴", "Not assessed": "⚪"}
SEVERITY_COLORS = {"High": "#c62828", "Medium": "#f9a825", "Low": "#1565c0"}


def _money(value) -> str:
    return f"PKR {value:,.0f}"


def _progress(engagement_id, summary) -> list:
    findings = findings_summary(engagement_id)
    reports = list_reports(engagement_id)
    has_data = not summary["tb"].empty or not summary["ledger"].empty
    exceptions = summary["exceptions"]
    tests_saved = findings["total"] > 0 or (exceptions is not None and len(exceptions) == 0)
    reviewed = findings["total"] > 0 and findings["counts"]["Pending Review"] == 0
    return [
        ("Data uploaded", has_data),
        ("Tests run and saved", tests_saved),
        ("Findings reviewed", reviewed),
        ("AI analysis run", bool(load_agent_results(engagement_id))),
        ("Report submitted", bool(reports)),
        ("Report approved", any(r["status"] == "Approved" for r in reports)),
    ]


def show_dashboard():
    settings = get_settings()
    username = st.session_state.get("user_name", "")
    hero(
        f"Welcome{', ' + username if username else ''}",
        "AI-assisted financial audit and internal control support for Pakistani businesses, SMEs and audit teams.",
        chips=[
            ("AI connected" if settings.groq_api_key else "AI key missing", "ok" if settings.groq_api_key else "bad"),
            (settings.groq_model, "info"),
            ("Demo storage", "warn"),
        ],
    )

    with get_session() as session:
        counts = (
            session.query(Company).count(), session.query(Engagement).count(),
            session.query(Document).count(),
            session.query(Finding).filter(Finding.review_status == "Pending Review").count(),
        )
    cols = st.columns(4)
    cols[0].metric("Companies", counts[0])
    cols[1].metric("Engagements", counts[1])
    cols[2].metric("Documents", counts[2])
    cols[3].metric("Findings to review", counts[3])

    st.subheader("Engagement overview")
    if not list_engagements():
        st.info("No engagement yet. Start with Company Management, then Audit Engagements, then upload "
                "a file in the Document Upload Center (or use the built-in sample data).")
    else:
        engagement_id = pick_engagement()
        summary = summarize_engagement(engagement_id, current_answers(engagement_id))
        statements, exceptions, risk = summary["statements"], summary["exceptions"], summary["risk"]

        steps = _progress(engagement_id, summary)
        stepper(steps)
        st.caption(f"{sum(1 for _, done in steps if done)} of {len(steps)} steps complete")

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

    st.subheader("Recent activity")
    with get_session() as session:
        logs = session.query(AuditLog).order_by(AuditLog.id.desc()).limit(8).all()
    if logs:
        st.dataframe([
            {"Time (PKT)": (l.timestamp + timedelta(hours=5)).strftime("%Y-%m-%d %H:%M"),
             "User": l.username, "Action": l.action} for l in logs
        ], hide_index=True)
    else:
        st.info("No activity yet.")

    with st.expander("System check"):
        st.write(f"AI model in use: `{settings.groq_model}`")
        if st.button("Test Groq connection"):
            with st.spinner("Contacting Groq..."):
                try:
                    reply = LLMService().ask("Reply with the single word: OK")
                    st.success(f"Connected. The AI replied: {reply[:60]}")
                    log_activity("groq_connection_test", "success", username=username or "system")
                except LLMError as err:
                    st.error(str(err))
                    log_activity("groq_connection_test", f"failed: {err}", username=username or "system")
