"""Runs the agents with CrewAI and validates what they return."""
import json
import os
import time

from pydantic import ValidationError

from agents.facts import outputs_digest
from agents.qa_checks import check_all
from agents.schemas import SCHEMAS
from agents.specs import AGENT_SPECS, COMMON_RULES, FORMATS
from services.llm_service import LLMError


class AgentError(Exception):
    """A friendly error message for the user."""


def _clean(text: str) -> str:
    # CrewAI treats { } as placeholders, so we replace them.
    return text.replace("{", "(").replace("}", ")")


def _extract_json(raw: str) -> dict:
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("No JSON object was found in the reply.")
    return json.loads(raw[start:end + 1])


def _instructions(spec, facts_text: str, problem: str) -> str:
    parts = [
        spec.task, "", COMMON_RULES, "",
        "FACTS (the only information you may use):", facts_text, "",
        FORMATS[spec.schema],
    ]
    if problem:
        parts += ["", f"Your previous reply was rejected: {problem} "
                      "Reply again with one valid JSON object only."]
    return _clean("\n".join(parts))


def _call_crewai(spec, instructions: str) -> str:
    try:
        os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")  # keep financial data private
        os.environ.setdefault("OTEL_SDK_DISABLED", "true")
        from crewai import Agent, Crew, Process, Task

        from agents.groq_llm import GroqCrewLLM
    except Exception as err:
        raise AgentError(
            f"CrewAI could not be loaded ({type(err).__name__}: {err}). "
            "Check the app logs and requirements.txt."
        ) from err

    try:
        llm = GroqCrewLLM()
        agent = Agent(
            role=spec.role, goal=spec.goal, backstory=spec.backstory,
            llm=llm, allow_delegation=False, verbose=False, max_iter=3,
        )
        task = Task(description=instructions, expected_output="One valid JSON object only.", agent=agent)
        crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)
        result = crew.kickoff()
    except LLMError as err:
        raise AgentError(str(err)) from err
    except Exception as err:
        raise AgentError(f"The agent run failed: {err}") from err
    return getattr(result, "raw", None) or str(result)


def run_agent(agent_key: str, facts_text: str) -> dict:
    spec = AGENT_SPECS[agent_key]
    schema = SCHEMAS[spec.schema]
    started = time.time()
    problem = ""
    for _ in range(2):
        raw = _call_crewai(spec, _instructions(spec, facts_text, problem))
        try:
            data = schema.model_validate(_extract_json(raw))
            return {"output": data.model_dump(), "seconds": round(time.time() - started, 1)}
        except (ValueError, ValidationError) as err:
            problem = str(err)[:400]
    raise AgentError(f"The AI did not return a valid answer twice. Please try again. Last problem: {problem}")


def run_qa(pack, outputs: dict) -> dict:
    """Automatic checks first (plain Python), then the QA agent comments on the rest."""
    checked = {key: value["output"] for key, value in outputs.items() if key != "qa"}
    issues = check_all(checked, pack.all_text(), pack.ids())
    issue_text = "\n".join(f"- {i['agent']}: {i['type']}: {i['detail']}" for i in issues) or "None found."
    key_facts = pack.text(["data_quality", "statements", "exceptions_brief"])
    text = (f"AUTOMATIC CHECK RESULTS:\n{issue_text}\n\n"
            f"SPECIALIST OUTPUTS:\n{outputs_digest(checked)}\n\nKEY FACTS:\n{key_facts}")
    result = run_agent("qa", text)
    comment = result["output"]
    status = "Needs review" if issues or comment["verdict"] == "Needs review" else "Pass"
    return {"output": comment, "issues": issues, "status": status, "seconds": result["seconds"]}
