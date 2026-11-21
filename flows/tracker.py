"""Progress board for a full audit run. Safe to use from several threads."""
import threading
import time

from agents.specs import AGENT_SPECS

SPECIALISTS = ["data_analyst", "audit_planner", "transaction_tester",
               "ratio_analyst", "internal_control", "ifrs_researcher"]
STEP_ORDER = ["checkpoint_data"] + SPECIALISTS + ["checkpoint_agents", "reporting", "qa"]


def step_label(key: str) -> str:
    if key == "checkpoint_data":
        return "Checkpoint 1: data validation"
    if key == "checkpoint_agents":
        return "Checkpoint 2: check the specialist results"
    return f"{AGENT_SPECS[key].number}. {AGENT_SPECS[key].name}"


class RunTracker:
    def __init__(self, engagement_id, checkpoint: dict, max_parallel: int = 2):
        self.engagement_id = engagement_id
        self.checkpoint = checkpoint
        self.gate = threading.Semaphore(max(1, int(max_parallel)))
        self._lock = threading.RLock()
        self._began = {}
        self.status = {key: "pending" for key in STEP_ORDER}
        self.detail = {key: "" for key in STEP_ORDER}
        self.seconds = {}
        self.results = {}
        self.log_lines = []
        self.pre_issues = []
        self.running = True
        self.merged = False
        self.error = ""
        self.started = time.time()
        self.finished = None

    def mark(self, key, status, detail=""):
        with self._lock:
            now = time.time()
            if status == "running":
                self._began[key] = now
            if status in ("done", "failed") and key in self._began:
                self.seconds[key] = round(now - self._began[key], 1)
            self.status[key] = status
            if detail:
                self.detail[key] = detail

    def finish(self, key, result):
        with self._lock:
            self.results[key] = result
        self.mark(key, "done", f"{result.get('seconds', '?')} s")

    def fail(self, key, message):
        self.mark(key, "failed", message)
        self.log(f"{step_label(key)} failed: {message}")

    def skip(self, key, reason):
        self.mark(key, "skipped", reason)
        self.log(f"{step_label(key)} skipped: {reason}")

    def log(self, text):
        with self._lock:
            self.log_lines.append(f"{time.strftime('%H:%M:%S')}  {text}")

    def outputs_snapshot(self) -> dict:
        with self._lock:
            return dict(self.results)

    def success_count(self) -> int:
        with self._lock:
            return len(self.results)

    def finish_run(self, error=""):
        with self._lock:
            self.running = False
            self.finished = time.time()
            if error:
                self.error = error

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "status": dict(self.status), "detail": dict(self.detail), "seconds": dict(self.seconds),
                "results": dict(self.results), "log": list(self.log_lines),
                "running": self.running, "error": self.error, "checkpoint": self.checkpoint,
                "elapsed": round((self.finished or time.time()) - self.started),
            }
