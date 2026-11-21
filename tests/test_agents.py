import pytest
from pydantic import ValidationError

from agents.facts import build_fact_pack
from agents.qa_checks import check_output
from agents.runner import _extract_json
from agents.schemas import AgentReport
from models.database import init_db
from services.control_questionnaire import QUESTIONS, score_areas
from services.knowledge_base import search_knowledge
from services.sample_loader import load_sample_data


def _pack(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'agents.db'}")
    init_db()
    try:
        return build_fact_pack(load_sample_data())
    except FileNotFoundError:
        pytest.skip("Sample files not added yet")


def test_json_is_found_inside_extra_text():
    raw = 'Thought: ok\nFinal Answer: ```json\n{"summary": "A short summary text.", "key_points": ["a"]}\n```'
    assert AgentReport.model_validate(_extract_json(raw)).key_points == ["a"]


def test_bad_rating_level_is_rejected():
    with pytest.raises(ValidationError):
        AgentReport(summary="A long enough summary.", ratings=[{"item": "x", "level": "Extreme", "reason": "y"}])


def test_fact_pack_contains_expected_facts(tmp_path, monkeypatch):
    pack = _pack(tmp_path, monkeypatch)
    assert "PAY-2002" in pack.sections["exceptions"]
    assert "PKR 3,250,000" in pack.sections["statements"]
    assert "Current Ratio: 2.14" in pack.sections["ratios"]
    assert "EX-001" in pack.ids()


def test_agents_wait_for_their_data(tmp_path, monkeypatch):
    pack = _pack(tmp_path, monkeypatch)
    assert pack.input_for("reporting", {})[1] != ""
    assert pack.input_for("qa", {})[1] != ""
    assert pack.input_for("transaction_tester", {})[1] == ""


def test_qa_flags_made_up_numbers_and_sources():
    output = {"summary": "Net profit is PKR 3,250,000 but costs are PKR 9,999,999.", "sources_used": ["FS-9"]}
    issues = check_output("Test agent", output, {3250000.0}, {"FS-1"})
    types = [i["type"] for i in issues]
    assert "Unsupported number" in types and "Unknown source" in types
    assert all("3,250,000" not in i["detail"] for i in issues)


def test_qa_flags_accusing_words():
    output = {"summary": "This proves the payment was made twice.", "sources_used": ["FS-1"]}
    issues = check_output("Test agent", output, set(), {"FS-1"})
    assert any(i["type"] == "Risky wording" for i in issues)


def test_questionnaire_scoring():
    answers = {area: [(q, "Yes") for q in qs] for area, qs in QUESTIONS.items()}
    assert all(r["score"] == 100 and r["risk"] == "Low" for r in score_areas(answers))
    answers["Payments"][0] = (answers["Payments"][0][0], "Not answered")
    assert next(r for r in score_areas(answers) if r["area"] == "Payments")["risk"] == "Incomplete"


def test_knowledge_search_finds_the_right_standard():
    results = search_knowledge("inventory measurement net realisable value cost", k=2)
    if not results:
        pytest.skip("Knowledge base file not added yet")
    assert "IAS 2" in results[0].location
