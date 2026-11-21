import pytest

from flows.checkpoints import run_data_checkpoint
from flows.tracker import STEP_ORDER, RunTracker
from models.database import init_db
from services.engagement_service import get_or_create_engagement
from services.sample_loader import load_sample_data


def test_tracker_records_progress():
    tracker = RunTracker(1, {"passed": True, "checks": []}, 2)
    tracker.mark("data_analyst", "running")
    tracker.finish("data_analyst", {"output": {}, "seconds": 1.5})
    tracker.fail("ratio_analyst", "boom")
    tracker.skip("internal_control", "no data")
    snap = tracker.snapshot()
    assert snap["status"]["data_analyst"] == "done"
    assert snap["status"]["ratio_analyst"] == "failed"
    assert snap["status"]["internal_control"] == "skipped"
    assert tracker.success_count() == 1
    assert set(snap["status"]) == set(STEP_ORDER)


def test_checkpoint_blocks_an_empty_engagement(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'flow.db'}")
    init_db()
    result = run_data_checkpoint(get_or_create_engagement("Empty Co", "Audit"))
    assert result["passed"] is False
    assert any(c["status"] == "fail" for c in result["checks"])


def test_checkpoint_passes_sample_data_with_a_warning(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'flow.db'}")
    init_db()
    try:
        engagement_id = load_sample_data()
    except FileNotFoundError:
        pytest.skip("Sample files not added yet")
    result = run_data_checkpoint(engagement_id)
    assert result["passed"] is True
    assert any("not in the trial balance" in c["detail"] for c in result["checks"])


def test_blocked_data_stops_the_flow_before_any_agent_runs():
    pytest.importorskip("crewai")
    from flows.audit_flow import _worker

    tracker = RunTracker(1, {"passed": False, "checks": []}, 1)
    _worker(tracker, None)
    assert tracker.status["checkpoint_data"] == "failed"
    assert tracker.status["data_analyst"] == "pending"
    assert tracker.running is False
    assert tracker.error == ""
