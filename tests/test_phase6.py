import pytest

from agents.facts import build_fact_pack
from models.database import init_db
from services import chat_service
from services.risk_engine import calculate_risk, control_risk, financial_risk, level_for, transaction_risk
from services.sample_loader import load_sample_data
from services.transaction_checks import ExceptionItem


def _exception(severity):
    return ExceptionItem(test="t", severity=severity, title="x", references="r", method="m",
                         explanation="e", evidence="v")


def _statements(**overrides):
    base = {"current_assets": 200.0, "current_liabilities": 100.0, "net_profit": 10.0, "total_equity": 100.0,
            "total_liabilities": 100.0, "equation_difference": 0.0, "revenue": 500.0}
    base.update(overrides)
    return base


def test_levels():
    assert (level_for(10), level_for(34), level_for(66.9), level_for(67)) == ("Low", "Medium", "Medium", "High")


def test_transaction_risk_points():
    area = transaction_risk([_exception("High")] * 3 + [_exception("Medium")])
    assert area["score"] == 68 and area["level"] == "High"
    assert transaction_risk([])["score"] == 0
    assert transaction_risk(None)["assessed"] is False


def test_financial_risk_rules():
    assert financial_risk(_statements())["score"] == 0
    weak = financial_risk(_statements(current_assets=50.0, net_profit=-5.0))
    assert weak["score"] == 60 and weak["level"] == "Medium"


def test_control_risk_uses_only_fully_answered_areas():
    rows = [
        {"area": "A", "score": 100.0, "risk": "Low"},
        {"area": "B", "score": 0.0, "risk": "High"},
        {"area": "C", "score": 50.0, "risk": "Incomplete"},
    ]
    area = control_risk(rows)
    assert area["score"] == 50.0
    assert any("Incomplete" in d or "incomplete" in d for d in area["drivers"])
    assert control_risk(None)["assessed"] is False


def test_overall_rebalances_missing_areas():
    result = calculate_risk(None, [_exception("High")] * 2, None, None)
    assert result["overall_score"] == 40.0  # only the Transactions area is assessed
    assert calculate_risk(None, None, None, None)["overall_score"] is None


def test_chat_flags_made_up_numbers_and_sources(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'p6.db'}")
    init_db()
    try:
        pack = build_fact_pack(load_sample_data())
    except FileNotFoundError:
        pytest.skip("Sample files not added yet")

    class FakeService:
        def chat(self, messages, temperature=None):
            return "Net profit is PKR 3,250,000 [FS-11] but costs are PKR 9,999,999 [FS-99]."

    monkeypatch.setattr(chat_service, "LLMService", FakeService)
    result = chat_service.answer_question(pack, "What is the net profit?", [])
    types = [i["type"] for i in result["issues"]]
    assert "Unsupported number" in types and "Unknown source" in types
    assert all("3,250,000" not in i["detail"] for i in result["issues"])
