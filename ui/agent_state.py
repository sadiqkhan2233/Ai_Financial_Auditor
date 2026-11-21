import streamlit as st

from models.database import log_activity
from services.control_questionnaire import collect_answers

ICONS = {"Low": "🟢", "Medium": "🟡", "High": "🔴"}


def outputs_for(engagement_id) -> dict:
    store = st.session_state.setdefault("agent_outputs", {})
    return store.setdefault(engagement_id, {})


def current_answers(engagement_id) -> dict:
    return collect_answers(st.session_state, engagement_id)


def run_and_store(engagement_id, agent_key):
    """Runs one agent. Returns (True, '') or (False, 'message')."""
    try:
        from agents.facts import build_fact_pack
        from agents.runner import AgentError, run_agent, run_qa
    except Exception as err:
        return False, f"Could not load the agent tools: {err}"

    outputs = outputs_for(engagement_id)
    pack = build_fact_pack(engagement_id, current_answers(engagement_id))
    text, problem = pack.input_for(agent_key, outputs)
    if problem:
        return False, problem
    try:
        result = run_qa(pack, outputs) if agent_key == "qa" else run_agent(agent_key, text)
    except AgentError as err:
        return False, str(err)
    except Exception as err:
        return False, f"Unexpected error: {err}"
    outputs[agent_key] = result
    log_activity("agent_run", f"{agent_key} on engagement {engagement_id}")
    return True, ""


def _bullets(title, items):
    if items:
        st.markdown(f"**{title}**")
        st.markdown("\n".join(f"- {item}" for item in items))


def report_to_markdown(r: dict) -> str:
    lines = [f"# {r['title']}", "", "## Executive summary", r["executive_summary"], "",
             "## Scope and data", r["scope_and_data"], "", "## Key findings"]
    lines += [f"- {x}" for x in r["key_findings"]]
    lines += ["", "## Risk assessment", r["risk_assessment"], "", "## Recommendations"]
    lines += [f"- {x}" for x in r["recommendations"]]
    lines += ["", "## Limitations", r["limitations"], "",
              "_Draft for review by a qualified auditor. This is not an audit opinion._"]
    return "\n".join(lines)


def render_result(agent_key: str, result: dict):
    out = result["output"]
    st.caption(f"Finished in {result.get('seconds', '?')} seconds.")

    if agent_key == "reporting":
        st.subheader(out["title"])
        st.markdown("**Executive summary**")
        st.write(out["executive_summary"])
        st.markdown("**Scope and data**")
        st.write(out["scope_and_data"])
        _bullets("Key findings", out["key_findings"])
        st.markdown("**Risk assessment**")
        st.write(out["risk_assessment"])
        _bullets("Recommendations", out["recommendations"])
        st.caption(f"Limitations: {out['limitations']}")
        st.download_button("Download draft report (Markdown)", report_to_markdown(out).encode("utf-8"),
                           file_name="audit_support_report_draft.md", mime="text/markdown")
        return

    if agent_key == "qa":
        if result["status"] == "Pass":
            st.success("QA status: Pass. No problems were found.")
        else:
            st.warning("QA status: Needs review.")
        if result["issues"]:
            st.markdown("**Automatic checks (plain Python)**")
            st.dataframe([{"Agent": i["agent"], "Type": i["type"], "Detail": i["detail"]}
                          for i in result["issues"]], hide_index=True)
        else:
            st.info("The automatic checks found no unsupported numbers, unknown sources or risky wording.")
        st.markdown("**QA agent's comments**")
        st.write(f"Verdict: {out['verdict']}")
        _bullets("Issues", out["issues"])
        if out["notes"]:
            st.write(out["notes"])
        return

    st.write(out["summary"])
    _bullets("Key points", out["key_points"])
    _bullets("Concerns", out["concerns"])
    _bullets("Recommended actions", out["recommended_actions"])
    if out["ratings"]:
        st.markdown("**Ratings**")
        st.dataframe([{"Item": r["item"], "Level": f"{ICONS[r['level']]} {r['level']}", "Reason": r["reason"]}
                      for r in out["ratings"]], hide_index=True)
    if out["sources_used"]:
        st.caption("Facts used: " + ", ".join(out["sources_used"]))
    if out["limitations"]:
        st.caption(f"Limitations: {out['limitations']}")
