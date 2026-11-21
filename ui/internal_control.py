import plotly.express as px
import streamlit as st

from services.control_questionnaire import ANSWERS, QUESTIONS, answer_key, score_areas
from ui.agent_state import current_answers, outputs_for, render_result, run_and_store
from ui.common import pick_engagement

ICONS = {"Low": "🟢", "Medium": "🟡", "High": "🔴", "Incomplete": "⚪", "Not assessed": "⚪"}


def show_internal_control():
    st.title("🛡️ Internal Control Assessment")
    st.caption("Answer the questions about the company's controls. Scores are simple maths: Yes = 1 point, "
               "Partly = half a point. The AI agent then explains the result.")

    engagement_id = pick_engagement()
    if engagement_id is None:
        return

    saved = st.session_state.setdefault("control_saved", {})
    for area, questions in QUESTIONS.items():
        with st.expander(area):
            for index, question in enumerate(questions):
                key = answer_key(engagement_id, area, index)
                current = saved.get(key, "Not answered")
                saved[key] = st.radio(question, ANSWERS, index=ANSWERS.index(current),
                                      horizontal=True, key=f"widget_{key}")

    st.subheader("Preliminary results")
    scores = score_areas(current_answers(engagement_id))
    st.dataframe([
        {"Area": r["area"], "Yes": r["yes"], "Partly": r["partly"], "No": r["no"],
         "Don't know": r["unknown"], "Not answered": r["unanswered"], "Score %": r["score"],
         "Preliminary control risk": f"{ICONS[r['risk']]} {r['risk']}"}
        for r in scores
    ], hide_index=True)
    st.plotly_chart(px.bar([{"Area": r["area"], "Score %": r["score"]} for r in scores],
                           x="Area", y="Score %", range_y=[0, 100], title="Control score by area"))
    st.caption("Risk bands: 80% or more = Low, 50% to under 80% = Medium, under 50% = High. These are starting "
               "points for the auditor's judgement. Areas with unanswered questions are not rated.")

    st.subheader("AI explanation")
    if st.button("Run the Internal Control Assessment Agent", type="primary"):
        with st.spinner("The agent is working. This can take up to a minute..."):
            ok, message = run_and_store(engagement_id, "internal_control")
        if not ok:
            st.error(message)
    result = outputs_for(engagement_id).get("internal_control")
    if result:
        render_result("internal_control", result)
