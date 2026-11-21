"""Data validation checkpoint. Plain Python, no AI."""
from services.account_classifier import classify_trial_balance
from services.data_access import load_transactions, load_trial_balance
from services.ratio_engine import add_balances, build_statements


def _add(checks, name, status, detail):
    checks.append({"check": name, "status": status, "detail": detail})


def run_data_checkpoint(engagement_id: int) -> dict:
    tb = load_trial_balance(engagement_id)
    ledger = load_transactions(engagement_id)
    checks, blocking = [], False

    if tb.empty:
        _add(checks, "Trial balance saved", "fail",
             "No trial balance is saved. Upload one in the Document Upload Center. "
             "(For a ledger-only review, use the 'Run one agent' tab.)")
        blocking = True
    else:
        _add(checks, "Trial balance saved", "pass", f"{len(tb)} accounts.")
        difference = round(float(tb["debit"].sum() - tb["credit"].sum()), 2)
        if abs(difference) > 0.01:
            _add(checks, "Debits equal credits", "fail", f"The trial balance is out by PKR {difference:,.2f}.")
            blocking = True
        else:
            _add(checks, "Debits equal credits", "pass", "The trial balance balances.")

        classified = classify_trial_balance(tb)
        unclassified = classified.loc[classified["category"] == "Unclassified", "account_name"].tolist()
        if unclassified:
            _add(checks, "All accounts grouped", "warn",
                 f"{len(unclassified)} account(s) could not be grouped: {', '.join(unclassified[:5])}. "
                 "They are left out of the ratios.")
        else:
            _add(checks, "All accounts grouped", "pass", "Every account was grouped automatically.")

        statements = build_statements(add_balances(classified))
        if abs(statements["equation_difference"]) > 1:
            _add(checks, "Assets = liabilities + equity", "warn",
                 f"After automatic grouping they differ by PKR {statements['equation_difference']:,.0f}. "
                 "Ratios may be unreliable; review the groups on the Financial Analysis page.")
        else:
            _add(checks, "Assets = liabilities + equity", "pass", "The balance sheet equation holds.")
        if statements["revenue"] <= 0:
            _add(checks, "Revenue found", "warn", "No revenue was found, so margins cannot be calculated.")

    if ledger.empty:
        _add(checks, "General ledger saved", "warn",
             "No general ledger is saved. Transaction testing and control signals will be skipped.")
    else:
        _add(checks, "General ledger saved", "pass", f"{len(ledger)} lines.")
        if ledger["date"].dropna().empty:
            _add(checks, "Ledger dates", "warn", "No valid dates were found in the ledger.")
        if not tb.empty:
            tb_names = {name.strip().lower() for name in tb["account_name"]}
            ledger_names = {name.strip().lower() for name in ledger["account"] if name.strip()}
            missing = sorted(ledger_names - tb_names)
            if missing:
                _add(checks, "Ledger accounts exist in trial balance", "warn",
                     f"{len(missing)} ledger account name(s) are not in the trial balance: "
                     f"{', '.join(missing[:5])}. Worth asking the client about.")
            else:
                _add(checks, "Ledger accounts exist in trial balance", "pass",
                     "Every ledger account appears in the trial balance.")

    return {"passed": not blocking, "checks": checks}
