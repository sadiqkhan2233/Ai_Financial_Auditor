from collections import Counter

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from services.engagement_summary import summarize_engagement
from services.ratio_engine import review_points
from services.risk_engine import WEIGHTS
from ui.agent_state import current_answers
from ui.common import pick_engagement

ICONS = {"Low": "🟢", "Medium": "🟡", "High": "🔴", "Not assessed": "⚪"}
COLORS = {"Low": "#2e7d32", "Medium": "#f9a825", "High": "#c62828"}


def _gauge(score, level):
    figure = go.Figure(go.Indicator(
        mode="gauge+number", value=score, title={"text": f"Overall preliminary risk: {level}"},
        gauge={"axis": {"range": [0, 100]}, "bar": {"color": COLORS.get(level, "#555555")},
               "steps": [{"range": [0, 34], "color": "#d4edda"},
                         {"range": [34, 67], "color": "#fff3cd"},
                         {"range": [67, 100], "color": "#f8d7da"}]},
    ))
    figure.update_layout(height=300, margin={"t": 60, "b": 10})
    return figure


def show_risk_dashboard():
    st.title("⚠️ Audit Risk Dashboard")
    st.caption("A preliminary risk picture built with simple scoring rules. It supports the auditor's "
               "judgement and is not an audit opinion.")

    engagement_id = pick_engagement()
    if engagement_id is None:
        return
    summary = summarize_engagement(engagement_id, current_answers(engagement_id))
    risk = summary["risk"]
    if risk["overall_score"] is None:
        st.info("There is nothing to score yet. Save a trial balance or a general ledger first.")
        return

    left, right = st.columns([1, 2])
    left.plotly_chart(_gauge(risk["overall_score"], risk["overall_level"]))
    with right:
        cards = st.columns(4)
        for card, area in zip(cards, risk["areas"]):
            value = f"{area['score']:.0f} / 100" if area["assessed"] else "Not assessed"
            card.metric(f"{ICONS[area['level']]} {area['area']}", value)
        if any(not a["assessed"] for a in risk["areas"]):
            st.caption("Areas that are 'Not assessed' are left out and the weights are rebalanced. "
                       "Answer the Internal Control Assessment questionnaire to include controls.")

    table = pd.DataFrame([
        {"Area": a["area"], "Score": a["score"], "Level": a["level"]} for a in risk["areas"] if a["assessed"]
    ])
    if not table.empty:
        st.plotly_chart(px.bar(table, x="Area", y="Score", color="Level", color_discrete_map=COLORS,
                               range_y=[0, 100], title="Risk score by area (higher means riskier)"))

    st.subheader("What drives each score")
    for area in risk["areas"]:
        with st.expander(f"{ICONS[area['level']]} {area['area']}"):
            st.markdown("\n".join(f"- {d}" for d in area["drivers"]))

    exceptions = summary["exceptions"]
    if exceptions:
        st.subheader("Exceptions")
        c1, c2 = st.columns(2)
        severity = [{"Severity": s, "Exceptions": sum(1 for e in exceptions if e.severity == s)}
                    for s in ("High", "Medium", "Low")]
        c1.plotly_chart(px.bar(severity, x="Severity", y="Exceptions", color="Severity",
                               color_discrete_map={"High": "#c62828", "Medium": "#f9a825", "Low": "#1565c0"},
                               title="By severity"))
        by_test = Counter(e.test for e in exceptions)
        c2.plotly_chart(px.bar([{"Test": k, "Exceptions": v} for k, v in by_test.items()],
                               x="Test", y="Exceptions", title="By test"))
        st.caption("Details are on the Transaction Testing page.")

    if summary["statements"]:
        points = review_points(summary["statements"])
        if points:
            st.subheader("Financial review points")
            for point in points:
                st.warning(point)

    csv = pd.DataFrame([
        {"Area": a["area"], "Score": a["score"], "Level": a["level"], "Drivers": " | ".join(a["drivers"])}
        for a in risk["areas"]
    ]).to_csv(index=False).encode("utf-8")
    st.download_button("Download risk summary (CSV)", csv, file_name="risk_summary.csv", mime="text/csv")

    with st.expander("How the scores are calculated"):
        st.markdown(
            "- **Transactions:** 20 points per High exception, 8 per Medium, 2 per Low (maximum 100).\n"
            "- **Financial position:** current ratio below 1.0 (+30) or below 1.5 (+15); net loss (+30); "
            "zero or negative equity (+30); debt-to-equity above 2.0 (+15); balance sheet does not balance (+10); "
            "no revenue (+10).\n"
            "- **Internal controls:** 100 minus the average questionnaire score of fully answered areas.\n"
            "- **Data quality:** 60 points per failed data check and 15 per warning.\n"
            "- **Overall:** weighted average using "
            + ", ".join(f"{name} {weight:.0%}" for name, weight in WEIGHTS.items())
            + ". Low is under 34, Medium is 34 to 66, High is 67 or more."
        )
