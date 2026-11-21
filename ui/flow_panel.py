import time

import streamlit as st

from agents.facts import build_fact_pack
from flows.checkpoints import run_data_checkpoint
from flows.tracker import SPECIALISTS, STEP_ORDER, step_label
from models.database import log_activity
from ui.agent_state import current_answers, outputs_for, render_result

STATUS_TEXT = {
    "pending": "⚪ Waiting", "waiting": "🕒 Queued", "running": "🔄 Running",
    "done": "✅ Done", "failed": "❌ Failed", "skipped": "⏭️ Skipped",
}
CHECK_ICONS = {"pass": "✅", "warn": "⚠️", "fail": "❌"}

WORKFLOW = """digraph G {
  rankdir=LR; node [shape=box, style=rounded];
  cp1 [label="Checkpoint 1\\ndata validation"];
  specialists [label="Six specialist agents\\n(side by side)"];
  cp2 [label="Checkpoint 2\\nautomatic checks"];
  report [label="Reporting agent"];
  qa [label="Quality assurance agent"];
  stop [label="Stop and explain", style="rounded,dashed"];
  cp1 -> specialists [label="passed"];
  cp1 -> stop [label="failed"];
  specialists -> cp2 -> report -> qa;
}"""


def _start(engagement_id, parallel):
    try:
        from flows.audit_flow import start_run
    except Exception as err:
        return None, f"The workflow engine could not be loaded ({type(err).__name__}: {err})."
    pack = build_fact_pack(engagement_id, current_answers(engagement_id))
    checkpoint = run_data_checkpoint(engagement_id)
    return start_run(engagement_id, pack, checkpoint, parallel), ""


def show_flow_panel(engagement_id):
    st.write("One click runs everything: a data check, the six specialist agents, a draft report and a "
             "quality review. It can take several minutes.")
    with st.expander("How the workflow runs"):
        st.graphviz_chart(WORKFLOW)
        st.caption("Free Groq plans limit how much text you can send per minute, so the number of agents "
                   "working at the same time is limited by the setting below.")

    runs = st.session_state.setdefault("flow_runs", {})
    tracker = runs.get(engagement_id)
    running = tracker is not None and tracker.running

    parallel = st.radio("How many agents may work at the same time?", [1, 2, 3], index=1, horizontal=True,
                        help="1 is slowest but safest. Higher numbers are faster but may hit Groq's limit.")
    if st.button("▶ Run complete audit analysis", type="primary", disabled=running):
        new_tracker, problem = _start(engagement_id, parallel)
        if problem:
            st.error(problem)
        else:
            runs[engagement_id] = new_tracker
            st.rerun()

    tracker = runs.get(engagement_id)
    if tracker is None:
        st.info("Nothing has been run yet for this engagement.")
        return
    snap = tracker.snapshot()

    st.subheader("Checkpoint 1: data validation")
    for check in snap["checkpoint"]["checks"]:
        st.write(f"{CHECK_ICONS[check['status']]} **{check['check']}**: {check['detail']}")

    finished = sum(1 for s in snap["status"].values() if s in ("done", "failed", "skipped"))
    st.progress(finished / len(STEP_ORDER), text=f"{finished} of {len(STEP_ORDER)} steps finished "
                                                  f"({snap['elapsed']} seconds)")
    st.dataframe([
        {"Step": step_label(key), "Status": STATUS_TEXT[snap["status"][key]], "Note": snap["detail"][key]}
        for key in STEP_ORDER
    ], hide_index=True)
    with st.expander("Activity log"):
        st.text("\n".join(snap["log"]) or "(empty)")

    if snap["running"]:
        st.caption("Working... this page refreshes by itself. You can leave it open.")
        time.sleep(2)
        st.rerun()
        return

    if snap["error"]:
        st.error(snap["error"])
    if not tracker.merged:
        outputs = outputs_for(engagement_id)
        for key, result in snap["results"].items():
            outputs[key] = result
        tracker.merged = True
        log_activity("full_audit_run", f"engagement {engagement_id}: {len(snap['results'])} result(s)")

    failed = [step_label(k) for k, s in snap["status"].items() if s == "failed"]
    if failed:
        st.warning("Some steps failed: " + "; ".join(failed) +
                   ". If the notes mention Groq's limit, set 'at the same time' to 1 and run again.")
    elif snap["status"]["qa"] == "done":
        st.success("The workflow finished. These are drafts for a qualified auditor to review.")

    outputs = outputs_for(engagement_id)
    if "qa" in outputs:
        st.subheader("Quality review")
        render_result("qa", outputs["qa"])
    if "reporting" in outputs:
        st.subheader("Draft report")
        render_result("reporting", outputs["reporting"])
    for key in SPECIALISTS:
        if key in outputs:
            with st.expander(step_label(key)):
                render_result(key, outputs[key])
