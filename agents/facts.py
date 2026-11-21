"""Builds the numbered fact sheets the agents are allowed to use."""
from collections import Counter
from dataclasses import dataclass

from agents.qa_checks import ID_RE
from agents.specs import ORDER
from services.account_classifier import classify_trial_balance
from services.control_questionnaire import any_answered, score_areas
from services.data_access import load_transactions, load_trial_balance
from services.knowledge_base import search_knowledge
from services.ratio_engine import (
    add_balances, break_even, build_statements, calculate_ratios, format_value, review_points,
)
from services.transaction_checks import run_all_tests

MAX_EXCEPTIONS = 15

SECTION_TITLES = {
    "data_quality": "Data quality facts",
    "statements": "Financial statement facts",
    "ratios": "Ratio facts",
    "planning": "Planning facts",
    "exceptions": "Transaction test exceptions",
    "exceptions_brief": "Transaction test exceptions (short)",
    "controls": "Internal control facts",
    "knowledge": "Knowledge-base passages",
}

# agent -> (sections that must exist, sections added when they exist)
AGENT_SECTIONS = {
    "data_analyst": (["data_quality"], []),
    "audit_planner": (["statements", "planning"], ["ratios", "exceptions_brief"]),
    "transaction_tester": (["exceptions"], []),
    "ratio_analyst": (["statements", "ratios"], []),
    "internal_control": (["controls"], []),
    "ifrs_researcher": (["knowledge"], []),
}
PROBLEMS = {
    "data_analyst": "Upload and save a trial balance or general ledger first.",
    "audit_planner": "This agent needs a saved trial balance.",
    "transaction_tester": "This agent needs a saved general ledger.",
    "ratio_analyst": "This agent needs a saved trial balance.",
    "internal_control": "Answer the questionnaire on the Internal Control Assessment page, or save a general ledger.",
    "ifrs_researcher": "Save a trial balance or general ledger first.",
}


class _Numbered:
    def __init__(self, prefix):
        self.prefix, self.count, self.lines = prefix, 0, []

    def add(self, text):
        self.count += 1
        self.lines.append(f"{self.prefix}-{self.count}: {text}")


def _diff(value: float) -> str:
    value = round(value, 2)
    return f"{(0.0 if value == 0 else value):,.2f}"


@dataclass
class FactPack:
    engagement_id: int
    sections: dict
    exceptions: list

    def text(self, names) -> str:
        parts = []
        for name in names:
            body = self.sections.get(name, "").strip()
            if body:
                parts.append(f"=== {SECTION_TITLES[name]} ===\n{body}")
        return "\n\n".join(parts)

    def all_text(self) -> str:
        return "\n\n".join(self.sections.values())

    def ids(self) -> set:
        return set(ID_RE.findall(self.all_text()))

    def input_for(self, agent_key: str, outputs: dict):
        """Returns (text, problem). If problem is not empty the agent cannot run yet."""
        if agent_key in AGENT_SECTIONS:
            required, optional = AGENT_SECTIONS[agent_key]
            if not all(self.sections.get(name, "").strip() for name in required):
                return "", PROBLEMS[agent_key]
            return self.text(required + optional), ""

        specialists = {k: v["output"] for k, v in outputs.items() if k in AGENT_SECTIONS}
        if agent_key == "reporting":
            if not specialists:
                return "", "Run at least one of the specialist agents (steps 1 to 6) first."
            base = self.text(["data_quality", "statements", "exceptions_brief"])
            return f"{base}\n\n=== Specialist agent outputs ===\n{outputs_digest(specialists)}", ""
        if agent_key == "qa":
            others = {k: v["output"] for k, v in outputs.items() if k != "qa"}
            if not others:
                return "", "Run at least one agent first, then ask QA to check it."
            return outputs_digest(others), ""
        return "", "Unknown agent."


def outputs_digest(outputs: dict) -> str:
    """Turns agent outputs into short readable text."""
    fields = ["summary", "executive_summary", "scope_and_data", "key_points", "key_findings", "concerns",
              "risk_assessment", "recommended_actions", "recommendations", "limitations"]
    blocks = []
    for key in ORDER:
        out = outputs.get(key)
        if not out:
            continue
        lines = [f"--- {key} ---"]
        for name in fields:
            value = out.get(name)
            if not value:
                continue
            if isinstance(value, list):
                lines.append(f"{name}:")
                lines += [f"  - {item}" for item in value]
            else:
                lines.append(f"{name}: {value}")
        ratings = out.get("ratings") or []
        if ratings:
            lines.append("ratings: " + "; ".join(f"{r['item']} = {r['level']}" for r in ratings))
        if out.get("sources_used"):
            lines.append("sources_used: " + ", ".join(out["sources_used"]))
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


# ---------- section builders ----------

def _data_quality(tb, ledger, classified, missing_refs) -> str:
    if tb.empty and ledger.empty:
        return ""
    dq = _Numbered("DQ")
    if tb.empty:
        dq.add("No trial balance has been saved for this engagement.")
    else:
        debit, credit = float(tb["debit"].sum()), float(tb["credit"].sum())
        dq.add(f"Trial balance: {len(tb)} accounts; total debits PKR {debit:,.0f}; "
               f"total credits PKR {credit:,.0f}; difference PKR {_diff(debit - credit)}.")
        unclassified = classified.loc[classified["category"] == "Unclassified", "account_name"].tolist()
        if unclassified:
            dq.add(f"{len(unclassified)} account(s) could not be grouped automatically: "
                   f"{', '.join(unclassified[:8])}.")
        else:
            dq.add("All trial balance accounts were grouped automatically into statement categories "
                   "(the grouping is a guess that a human should confirm).")
    if ledger.empty:
        dq.add("No general ledger has been saved for this engagement.")
    else:
        n = len(ledger)
        dq.add(f"General ledger: {n} lines; total debits PKR {ledger['debit'].sum():,.0f}; "
               f"total credits PKR {ledger['credit'].sum():,.0f}.")
        dates = ledger["date"].dropna()
        if not dates.empty:
            dq.add(f"Ledger dates run from {dates.min():%d %b %Y} to {dates.max():%d %b %Y}.")
        dq.add(f"{missing_refs} of {n} ledger lines ({missing_refs / n * 100:.1f}%) have no reference number.")
    return "\n".join(dq.lines)


def _statements(s) -> str:
    fs = _Numbered("FS")
    items = [
        ("Total assets", "total_assets"), ("Current assets", "current_assets"),
        ("Current liabilities", "current_liabilities"), ("Total liabilities", "total_liabilities"),
        ("Total equity (share capital and reserves plus current-period profit)", "total_equity"),
        ("Revenue", "revenue"), ("Cost of sales", "cost_of_sales"), ("Gross profit", "gross_profit"),
        ("Operating expenses", "operating_expenses"), ("Finance cost", "finance_cost"),
        ("Net profit", "net_profit"), ("Cash", "cash"), ("Receivables", "receivables"),
        ("Inventory", "inventory"),
    ]
    for label, key in items:
        fs.add(f"{label}: PKR {s[key]:,.0f}.")
    fs.add(f"Assets minus liabilities minus equity: PKR {_diff(s['equation_difference'])}.")
    return "\n".join(fs.lines)


def _ratios(s) -> str:
    rt = _Numbered("RT")
    for r in calculate_ratios(s):
        rt.add(f"{r['name']}: {format_value(r['value'], r['kind'])} (formula: {r['formula']}).")
    for point in review_points(s):
        rt.add(f"Review point: {point}")
    return "\n".join(rt.lines)


def _planning(s, classified) -> str:
    pl = _Numbered("PL")
    revenue, assets, profit = s["revenue"], s["total_assets"], s["net_profit"]
    if revenue > 0:
        pl.add(f"Materiality benchmark based on revenue (0.5% to 1%): PKR {revenue * 0.005:,.0f} "
               f"to PKR {revenue * 0.01:,.0f}.")
    if assets > 0:
        pl.add(f"Materiality benchmark based on total assets (1% to 2%): PKR {assets * 0.01:,.0f} "
               f"to PKR {assets * 0.02:,.0f}.")
    if profit > 0:
        pl.add(f"Materiality benchmark based on net profit (5%): PKR {profit * 0.05:,.0f}.")
    pl.add("These benchmarks are only common starting points. The auditor decides the actual materiality.")
    result = break_even(s)
    if result:
        pl.add(f"Estimated break-even revenue: PKR {result['break_even_revenue']:,.0f}; margin of safety "
               f"{result['margin_of_safety'] * 100:.1f}% (assumes cost of sales varies with sales and other "
               "costs are fixed).")
    top = classified.assign(bal=classified[["debit", "credit"]].max(axis=1)).sort_values("bal", ascending=False).head(6)
    for row in top.itertuples():
        pl.add(f"Large account balance: {row.account_name} ({row.category}) PKR {row.bal:,.0f}.")
    return "\n".join(pl.lines)


def _exceptions(exceptions, n_lines):
    high = sum(1 for e in exceptions if e.severity == "High")
    medium = sum(1 for e in exceptions if e.severity == "Medium")
    low = sum(1 for e in exceptions if e.severity == "Low")
    summary = (f"{n_lines} ledger lines were tested and {len(exceptions)} exception(s) were found: "
               f"{high} High, {medium} Medium, {low} Low. An exception is something to investigate, "
               "not proof of fraud.")
    lines = [
        f"{e.exception_id} [{e.severity}] {e.test}: {e.title}. References: {e.references}. {e.explanation}"[:450]
        for e in exceptions
    ]
    full = [summary] + lines[:MAX_EXCEPTIONS]
    if len(lines) > MAX_EXCEPTIONS:
        full.append(f"Only the first {MAX_EXCEPTIONS} of {len(lines)} exceptions are shown.")
    brief = [summary] + lines[:5]
    return "\n".join(full), "\n".join(brief)


def _controls(ledger, exceptions, missing_refs, answers) -> str:
    lines = []
    if not ledger.empty:
        counts = Counter(e.test for e in exceptions)
        ct = _Numbered("CT")
        ct.add(f"{missing_refs} of {len(ledger)} ledger lines have no reference number.")
        ct.add(f"Duplicate checks found {counts['Exact duplicate']} exact duplicate group(s) and "
               f"{counts['Near-duplicate']} near-duplicate pair(s).")
        ct.add(f"Manual or adjusting journal entry exceptions: {counts['Unusual journal entry']}.")
        ct.add(f"Timing exceptions (weekend or year-end): {counts['Unusual timing']}.")
        lines += ct.lines
    if answers and any_answered(answers):
        cq = _Numbered("CQ")
        for row in score_areas(answers):
            cq.add(f"{row['area']}: Yes {row['yes']}, Partly {row['partly']}, No {row['no']}, "
                   f"Don't know {row['unknown']}, not answered {row['unanswered']}; "
                   f"score {row['score']:.1f}%; preliminary control risk: {row['risk']}.")
        for area, items in answers.items():
            for question, answer in items:
                if answer in ("Partly", "No", "Don't know"):
                    cq.add(f"{area}: {question} Answer: {answer}.")
        lines += cq.lines
    elif lines:
        lines.append("The control questionnaire has not been answered yet.")
    return "\n".join(lines)


def _knowledge(statements, classified, exceptions, answers) -> str:
    topics = [
        ("Audit evidence", "audit evidence sufficient appropriate reliable"),
        ("Materiality", "materiality overall performance benchmark"),
    ]
    if statements:
        if statements["inventory"] > 0:
            topics.append(("Inventory", "inventory measurement net realisable value cost"))
        if statements["receivables"] > 0:
            topics.append(("Receivables", "trade receivables expected credit loss impairment"))
        if statements["revenue"] > 0:
            topics.append(("Revenue", "revenue recognition control customer cut-off"))
        if statements["non_current_assets"] > 0:
            topics.append(("Fixed assets", "property plant equipment depreciation useful life"))
        weak_liquidity = (statements["current_liabilities"] > statements["current_assets"]
                          or statements["net_profit"] < 0)
        if weak_liquidity:
            topics.append(("Going concern", "going concern twelve months material uncertainty"))
    if classified is not None:
        names = " ".join(classified["account_name"].str.lower())
        if "rent" in names or "lease" in names:
            topics.append(("Leases", "lease right-of-use asset liability rent"))
    if any(e.test in ("Unusual journal entry", "Missing reference") for e in exceptions):
        topics.append(("Journal entries and fraud risk", "journal entries management override fraud risk"))
    if answers and any_answered(answers):
        topics.append(("Internal control deficiencies", "internal control deficiencies communicate governance"))

    chosen, seen = [], set()
    for topic, query in topics:
        for chunk in search_knowledge(query, k=2):
            key = (chunk.source, chunk.location)
            if key not in seen:
                seen.add(key)
                chosen.append((topic, chunk))
    chosen = chosen[:8]

    lines = ["Topics searched: " + "; ".join(topic for topic, _ in topics) + "."]
    if not chosen:
        lines.append("No matching passages were found in the knowledge base.")
    for number, (topic, chunk) in enumerate(chosen, start=1):
        text = " ".join(chunk.text.split())[:700]
        lines.append(f"KB-{number}: [{chunk.source} > {chunk.location}] (topic: {topic}) {text}")
    return "\n".join(lines)


def build_fact_pack(engagement_id: int, control_answers: dict | None = None) -> FactPack:
    tb = load_trial_balance(engagement_id)
    ledger = load_transactions(engagement_id)
    have_tb, have_gl = not tb.empty, not ledger.empty
    sections = {name: "" for name in SECTION_TITLES}

    classified, statements, exceptions, missing_refs = None, None, [], 0
    if have_tb:
        classified = classify_trial_balance(tb)
        statements = build_statements(add_balances(classified))
    if have_gl:
        exceptions = run_all_tests(ledger)
        refs = ledger["reference"].fillna("").astype(str).str.strip()
        missing_refs = int((refs == "").sum())

    sections["data_quality"] = _data_quality(tb, ledger, classified, missing_refs)
    if have_tb:
        sections["statements"] = _statements(statements)
        sections["ratios"] = _ratios(statements)
        sections["planning"] = _planning(statements, classified)
    if have_gl:
        sections["exceptions"], sections["exceptions_brief"] = _exceptions(exceptions, len(ledger))
    sections["controls"] = _controls(ledger, exceptions, missing_refs, control_answers)
    if have_tb or have_gl:
        sections["knowledge"] = _knowledge(statements, classified, exceptions, control_answers)
    return FactPack(engagement_id, sections, exceptions)
