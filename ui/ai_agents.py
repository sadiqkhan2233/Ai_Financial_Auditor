import streamlit as st

from agents.facts import build_fact_pack
from agents.specs import AGENT_SPECS, ORDER
from config.settings import get_settings
from services.knowledge_base import list_sources
from ui.agent_state import current_answers, outputs_for, render_result, run_and_store
from ui.common import pick_engagement


def show_ai_agents():
    st.title("🤖 AI Audit Assistant: the eight agents")
    st.caption("Each agent only reads numbered facts that the app calculated. They explain; they never calculate. "
               "Run them one at a time. Phase 5 will chain them automatically.")
    st.warning("AI answers are drafts for a qualified auditor to review. They are not an audit opinion.")

    if not get_settings().groq_api_key:
        st.error("The Groq API key is missing. Add it in Streamlit Secrets.")
        return
    engagement_id = pick_engagement()
    if engagement_id is None:
        return

    outputs = outputs_for(engagement_id)
    pack = build_fact_pack(engagement_id, current_answers(engagement_id))

    choice = st.selectbox("Choose an agent", ORDER,
                          format_func=lambda key: f"{AGENT_SPECS[key].number}. {AGENT_SPECS[key].name}")
    spec = AGENT_SPECS[choice]
    st.write(f"**Needs:** {spec.needs}")

    text, problem = pack.input_for(choice, outputs)
    if problem:
        st.info(problem)
    with st.expander("See exactly what this agent will receive"):
        st.text(text or "(nothing yet)")
        if choice == "ifrs_researcher":
            sources = list_sources()
            st.caption("Knowledge base files: " + (", ".join(sources) if sources else "none found"))

    if st.button(f"Run: {spec.name}", type="primary", disabled=bool(problem)):
        with st.spinner("The agent is working. This can take up to a minute..."):
            ok, message = run_and_store(engagement_id, choice)
        if not ok:
            st.error(message)

    if choice in outputs:
        st.subheader("Result")
        render_result(choice, outputs[choice])

    st.subheader("Progress")
    st.dataframe([
        {"Step": AGENT_SPECS[k].number, "Agent": AGENT_SPECS[k].name,
         "Status": "✅ Done" if k in outputs else "Not run yet"}
        for k in ORDER
    ], hide_index=True)
    st.caption("Results are kept while this browser session is open. Saving them permanently comes in Phase 7.")
