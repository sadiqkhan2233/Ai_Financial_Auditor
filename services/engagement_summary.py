from flows.checkpoints import run_data_checkpoint
from services.account_classifier import classify_trial_balance
from services.control_questionnaire import any_answered, score_areas
from services.data_access import load_transactions, load_trial_balance
from services.ratio_engine import add_balances, build_statements
from services.risk_engine import calculate_risk
from services.transaction_checks import run_all_tests


def summarize_engagement(engagement_id: int, control_answers: dict | None = None) -> dict:
    tb = load_trial_balance(engagement_id)
    ledger = load_transactions(engagement_id)
    statements = build_statements(add_balances(classify_trial_balance(tb))) if not tb.empty else None
    exceptions = run_all_tests(ledger) if not ledger.empty else None
    controls = score_areas(control_answers) if control_answers and any_answered(control_answers) else None
    has_data = not tb.empty or not ledger.empty
    checkpoint = run_data_checkpoint(engagement_id) if has_data else None
    return {
        "tb": tb, "ledger": ledger, "statements": statements, "exceptions": exceptions,
        "controls": controls, "checkpoint": checkpoint,
        "risk": calculate_risk(statements, exceptions, controls, checkpoint),
    }
