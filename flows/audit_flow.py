"""The full audit workflow, built with CrewAI Flow."""
import os
import threading

os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")  # keep financial data private
os.environ.setdefault("OTEL_SDK_DISABLED", "true")
os.environ.setdefault("CREWAI_TRACING_ENABLED", "false")

from crewai.flow.flow import Flow, and_, listen, router, start  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from agents.qa_checks import check_all  # noqa: E402
from agents.runner import AgentError, run_agent, run_qa  # noqa: E402
from flows.tracker import RunTracker  # noqa: E402


class AuditState(BaseModel):
    stage: str = "starting"


class AuditFlow(Flow[AuditState]):
    # The page sets: self.audit_ctx (a RunTracker) and self.audit_pack (the fact sheets).

    def _run_specialist(self, key: str) -> str:
        ctx = self.audit_ctx
        text, problem = self.audit_pack.input_for(key, {})
        if problem:
            ctx.skip(key, problem)
            return "skipped"
        ctx.mark(key, "waiting")
        with ctx.gate:  # limits how many agents work at the same time
            ctx.mark(key, "running")
            try:
                ctx.finish(key, run_agent(key, text))
            except AgentError as err:
                ctx.fail(key, str(err))
            except Exception as err:
                ctx.fail(key, f"Unexpected error: {err}")
        return key

    # ---------- Checkpoint 1 ----------
    @start()
    def data_checkpoint(self):
        ctx = self.audit_ctx
        passed = ctx.checkpoint["passed"]
        ctx.mark("checkpoint_data", "done" if passed else "failed",
                 "Passed" if passed else "Blocked. See the checks above.")
        ctx.log("Checkpoint 1 (data validation): " + ("passed" if passed else "FAILED, analysis stopped"))
        self.state.stage = "data checked"
        return passed

    @router(data_checkpoint)
    def route_after_data(self):
        return "data_ok" if self.audit_ctx.checkpoint["passed"] else "data_blocked"

    @listen("data_blocked")
    def stop_blocked(self):
        self.audit_ctx.log("Stopped. Fix the data problems and run again.")
        self.state.stage = "stopped"
        return "stopped"

    # ---------- Specialist agents (they fan out from the same point) ----------
    @listen("data_ok")
    def agent_data_analyst(self):
        return self._run_specialist("data_analyst")

    @listen("data_ok")
    def agent_audit_planner(self):
        return self._run_specialist("audit_planner")

    @listen("data_ok")
    def agent_transaction_tester(self):
        return self._run_specialist("transaction_tester")

    @listen("data_ok")
    def agent_ratio_analyst(self):
        return self._run_specialist("ratio_analyst")

    @listen("data_ok")
    def agent_internal_control(self):
        return self._run_specialist("internal_control")

    @listen("data_ok")
    def agent_ifrs_researcher(self):
        return self._run_specialist("ifrs_researcher")

    # ---------- Checkpoint 2 (waits for all six) ----------
    @listen(and_(agent_data_analyst, agent_audit_planner, agent_transaction_tester,
                 agent_ratio_analyst, agent_internal_control, agent_ifrs_researcher))
    def specialist_checkpoint(self):
        ctx = self.audit_ctx
        outputs = {key: value["output"] for key, value in ctx.outputs_snapshot().items()}
        issues = check_all(outputs, self.audit_pack.all_text(), self.audit_pack.ids()) if outputs else []
        ctx.pre_issues = issues
        ctx.mark("checkpoint_agents", "done" if outputs else "failed",
                 f"{len(outputs)} agent(s) returned results; {len(issues)} automatic issue(s) noted")
        ctx.log(f"Checkpoint 2: {len(outputs)} specialist result(s), {len(issues)} automatic issue(s).")
        self.state.stage = "specialists finished"
        return len(outputs)

    @router(specialist_checkpoint)
    def route_after_specialists(self):
        return "reporting" if self.audit_ctx.success_count() else "no_results"

    @listen("no_results")
    def stop_no_results(self):
        self.audit_ctx.log("No agent returned a result, so no report was written. See the errors above.")
        self.state.stage = "stopped"
        return "stopped"

    # ---------- Report and QA ----------
    @listen("reporting")
    def agent_reporting(self):
        ctx = self.audit_ctx
        text, problem = self.audit_pack.input_for("reporting", ctx.outputs_snapshot())
        if problem:
            ctx.skip("reporting", problem)
            return "skipped"
        ctx.mark("reporting", "running")
        try:
            ctx.finish("reporting", run_agent("reporting", text))
        except AgentError as err:
            ctx.fail("reporting", str(err))
        except Exception as err:
            ctx.fail("reporting", f"Unexpected error: {err}")
        return "reporting"

    @listen(agent_reporting)
    def agent_qa(self):
        ctx = self.audit_ctx
        outputs = ctx.outputs_snapshot()
        if not outputs:
            ctx.skip("qa", "There was nothing to check.")
            return "skipped"
        ctx.mark("qa", "running")
        try:
            ctx.finish("qa", run_qa(self.audit_pack, outputs))
        except AgentError as err:
            ctx.fail("qa", str(err))
        except Exception as err:
            ctx.fail("qa", f"Unexpected error: {err}")
        return "qa"

    @listen(agent_qa)
    def finish(self):
        self.audit_ctx.log("Workflow finished.")
        self.state.stage = "finished"
        return "finished"


def _worker(tracker: RunTracker, pack) -> None:
    error = ""
    try:
        flow = AuditFlow()
        flow.audit_ctx = tracker
        flow.audit_pack = pack
        flow.kickoff()
    except Exception as err:
        error = f"The workflow stopped unexpectedly: {type(err).__name__}: {err}"
        tracker.log(error)
    finally:
        tracker.finish_run(error)


def start_run(engagement_id, pack, checkpoint: dict, max_parallel: int = 2) -> RunTracker:
    """Starts the workflow in the background and returns the progress board."""
    tracker = RunTracker(engagement_id, checkpoint, max_parallel)
    thread = threading.Thread(target=_worker, args=(tracker, pack), daemon=True)
    thread.start()
    return tracker
