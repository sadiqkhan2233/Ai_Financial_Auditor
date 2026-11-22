"""Preliminary risk scoring. Plain maths, no AI."""
from services.ratio_engine import safe_div

WEIGHTS = {"Transactions": 0.35, "Financial position": 0.25, "Internal controls": 0.25, "Data quality": 0.15}
RATED = ("Low", "Medium", "High")


def level_for(score: float) -> str:
    if score >= 67:
        return "High"
    if score >= 34:
        return "Medium"
    return "Low"


def _area(name, score, drivers):
    score = round(min(100.0, max(0.0, float(score))), 1)
    return {"area": name, "assessed": True, "score": score, "level": level_for(score), "drivers": drivers}


def _not_assessed(name, reason):
    return {"area": name, "assessed": False, "score": None, "level": "Not assessed", "drivers": [reason]}


def transaction_risk(exceptions):
    if exceptions is None:
        return _not_assessed("Transactions", "No general ledger is saved.")
    high = sum(1 for e in exceptions if e.severity == "High")
    medium = sum(1 for e in exceptions if e.severity == "Medium")
    low = sum(1 for e in exceptions if e.severity == "Low")
    drivers = []
    if high:
        drivers.append(f"{high} high-severity exception(s) x 20 points = {20 * high}")
    if medium:
        drivers.append(f"{medium} medium-severity exception(s) x 8 points = {8 * medium}")
    if low:
        drivers.append(f"{low} low-severity exception(s) x 2 points = {2 * low}")
    if not drivers:
        drivers.append("No exceptions were found.")
    return _area("Transactions", 20 * high + 8 * medium + 2 * low, drivers)


def financial_risk(statements):
    if statements is None:
        return _not_assessed("Financial position", "No trial balance is saved.")
    score, drivers = 0, []
    current_ratio = safe_div(statements["current_assets"], statements["current_liabilities"])
    if current_ratio is not None:
        if current_ratio < 1:
            score += 30
            drivers.append(f"Current ratio is below 1.0 ({current_ratio:.2f}): +30")
        elif current_ratio < 1.5:
            score += 15
            drivers.append(f"Current ratio is below 1.5 ({current_ratio:.2f}): +15")
    if statements["net_profit"] < 0:
        score += 30
        drivers.append("The company reports a net loss: +30")
    if statements["total_equity"] <= 0:
        score += 30
        drivers.append("Total equity is zero or negative: +30")
    elif safe_div(statements["total_liabilities"], statements["total_equity"]) > 2:
        score += 15
        drivers.append("Debt-to-equity is above 2.0: +15")
    if abs(statements["equation_difference"]) > 1:
        score += 10
        drivers.append("Assets do not equal liabilities plus equity after grouping: +10")
    if statements["revenue"] <= 0:
        score += 10
        drivers.append("No revenue was found: +10")
    if not drivers:
        drivers.append("None of the financial warning rules were triggered.")
    return _area("Financial position", score, drivers)


def control_risk(rows):
    if not rows:
        return _not_assessed("Internal controls", "The control questionnaire has not been answered.")
    rated = [r for r in rows if r["risk"] in RATED]
    if not rated:
        return _not_assessed("Internal controls", "No control area is fully answered yet.")
    score = sum(100 - r["score"] for r in rated) / len(rated)
    drivers = [f"{r['area']}: score {r['score']:.1f}% (control risk {r['risk']})" for r in rated]
    left_out = [r["area"] for r in rows if r["risk"] not in RATED]
    if left_out:
        drivers.append("Not included (incomplete): " + ", ".join(left_out))
    return _area("Internal controls", score, drivers)


def data_quality_risk(checkpoint):
    if not checkpoint:
        return _not_assessed("Data quality", "No data has been saved.")
    fails = [c for c in checkpoint["checks"] if c["status"] == "fail"]
    warns = [c for c in checkpoint["checks"] if c["status"] == "warn"]
    drivers = [f"{c['check']}: {c['detail']}" for c in fails + warns] or ["All data checks passed."]
    return _area("Data quality", 60 * len(fails) + 15 * len(warns), drivers)


def calculate_risk(statements, exceptions, control_rows, checkpoint) -> dict:
    areas = [
        transaction_risk(exceptions), financial_risk(statements),
        control_risk(control_rows), data_quality_risk(checkpoint),
    ]
    assessed = [a for a in areas if a["assessed"]]
    if not assessed:
        return {"areas": areas, "overall_score": None, "overall_level": "Not assessed"}
    total_weight = sum(WEIGHTS[a["area"]] for a in assessed)
    overall = round(sum(a["score"] * WEIGHTS[a["area"]] for a in assessed) / total_weight, 1)
    return {"areas": areas, "overall_score": overall, "overall_level": level_for(overall)}
