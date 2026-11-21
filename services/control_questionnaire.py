"""Internal control questionnaire and its scoring."""
from collections import Counter

ANSWERS = ["Not answered", "Yes", "Partly", "No", "Don't know"]

QUESTIONS = {
    "Authorization": [
        "Are purchases and expenses approved by someone with proper authority before they are committed?",
        "Is there a written approval limit that staff actually follow?",
        "Are manual journal entries approved by someone other than the person who prepared them?",
        "Are new vendors and changes to vendor bank details approved independently?",
    ],
    "Segregation of duties": [
        "Are the people who approve payments different from the people who record them?",
        "Is the person who handles cash different from the person who reconciles the bank?",
        "Is the person who creates vendors different from the person who processes payments?",
        "Is system access limited so each person can only do their own role?",
    ],
    "Purchasing": [
        "Are purchases supported by approved purchase orders?",
        "Are goods checked against the order and the invoice before the supplier is paid?",
        "Are quotations compared for major purchases?",
        "Are supplier invoices checked for duplicates before payment?",
    ],
    "Payments": [
        "Are payments made only against approved and supported invoices?",
        "Do payments need two authorised approvers or signatories?",
        "Are paid invoices marked or cancelled so they cannot be paid twice?",
        "Is each payment run reviewed against the approved list before release?",
    ],
    "Cash management": [
        "Are bank reconciliations prepared at least monthly?",
        "Are bank reconciliations reviewed by a senior person who did not prepare them?",
        "Is petty cash counted regularly and kept within a set limit?",
        "Are cash receipts deposited intact and promptly?",
    ],
}


def answer_key(engagement_id, area, index) -> str:
    return f"{engagement_id}|{area}|{index}"


def collect_answers(state, engagement_id) -> dict:
    saved = state.get("control_saved", {})
    return {
        area: [(q, saved.get(answer_key(engagement_id, area, i), "Not answered")) for i, q in enumerate(questions)]
        for area, questions in QUESTIONS.items()
    }


def any_answered(answers: dict) -> bool:
    return any(answer != "Not answered" for items in answers.values() for _, answer in items)


def score_areas(answers: dict) -> list:
    """Yes = 1 point, Partly = half a point, anything else = 0."""
    rows = []
    for area, items in answers.items():
        counts = Counter(answer for _, answer in items)
        total = len(items)
        unanswered = counts["Not answered"]
        score = round((counts["Yes"] + 0.5 * counts["Partly"]) / total * 100, 1) if total else 0.0
        if unanswered == total:
            risk = "Not assessed"
        elif unanswered:
            risk = "Incomplete"
        elif score >= 80:
            risk = "Low"
        elif score >= 50:
            risk = "Medium"
        else:
            risk = "High"
        rows.append({
            "area": area, "yes": counts["Yes"], "partly": counts["Partly"], "no": counts["No"],
            "unknown": counts["Don't know"], "unanswered": unanswered, "total": total,
            "score": score, "risk": risk,
        })
    return rows
