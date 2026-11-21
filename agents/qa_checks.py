"""Automatic quality checks on agent answers. Plain Python, no AI."""
import re

from agents.specs import AGENT_SPECS

ID_RE = re.compile(r"\b(?:DQ|FS|RT|EX|PL|CT|CQ|KB)-\d+\b")
ID_STRIP_RE = re.compile(r"\b[A-Z]{2,4}-\d+\b")
NUMBER_RE = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")

FORBIDDEN = [
    r"\bfraudulent\b", r"\bembezzl\w*", r"\btheft\b", r"\bstole\w*", r"\bguilty\b",
    r"\bproves?\b", r"\bproven\b", r"\bconfirmed fraud\b", r"\bcommitted fraud\b",
]


def _tokens(text: str) -> list:
    return NUMBER_RE.findall(ID_STRIP_RE.sub(" ", text))


def numbers_in(text: str) -> set:
    return {round(float(token.replace(",", "")), 2) for token in _tokens(text)}


def collect_strings(value, skip=("sources_used",)) -> list:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        out = []
        for key, item in value.items():
            if key not in skip:
                out += collect_strings(item, skip)
        return out
    if isinstance(value, list):
        out = []
        for item in value:
            out += collect_strings(item, skip)
        return out
    return []


def check_output(agent_name: str, output: dict, allowed_numbers: set, known_ids: set) -> list:
    issues = []
    text = " ".join(collect_strings(output))

    odd = []
    for token in _tokens(text):
        value = float(token.replace(",", ""))
        if "." not in token and value < 100:
            continue  # small whole numbers (counts, days, months) are not checked
        if round(value, 2) not in allowed_numbers:
            odd.append(token)
    if odd:
        shown = ", ".join(sorted(set(odd))[:8])
        issues.append({
            "agent": agent_name, "type": "Unsupported number",
            "detail": f"These numbers are not in the facts the agent was given: {shown}.",
        })

    for pattern in FORBIDDEN:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            issues.append({
                "agent": agent_name, "type": "Risky wording",
                "detail": f"The word '{match.group(0)}' is too strong. Exceptions are not proof of wrongdoing.",
            })

    sources = output.get("sources_used", [])
    if not sources:
        issues.append({"agent": agent_name, "type": "No sources", "detail": "The agent cited no fact IDs."})
    for source in sources:
        ids = ID_RE.findall(str(source))
        if not ids:
            issues.append({"agent": agent_name, "type": "Unknown source",
                           "detail": f"'{source}' is not a fact ID."})
        for fact_id in ids:
            if fact_id not in known_ids:
                issues.append({"agent": agent_name, "type": "Unknown source",
                               "detail": f"{fact_id} does not exist in the facts."})
    return issues


def check_all(outputs: dict, facts_text: str, known_ids: set) -> list:
    allowed = numbers_in(facts_text)
    issues = []
    for key, output in outputs.items():
        issues += check_output(AGENT_SPECS[key].name, output, allowed, known_ids)
    return issues
