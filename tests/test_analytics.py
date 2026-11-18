import pandas as pd
import pytest

from config.settings import BASE_DIR
from services.account_classifier import classify_account, classify_trial_balance
from services.document_processor import process_table, read_table
from services.ratio_engine import (
    add_balances, break_even, break_even_units, build_statements, calculate_ratios,
)
from services.transaction_checks import run_all_tests

SAMPLES = BASE_DIR / "data" / "sample_data"
COLUMNS = ["date", "reference", "description", "account", "vendor", "debit", "credit"]


def _load(name, doc_type):
    path = SAMPLES / name
    if not path.exists():
        pytest.skip("Sample files not added yet")
    clean, report = process_table(read_table(path.name, path.read_bytes()), doc_type)
    assert report.passed
    return clean


def _statements():
    tb = _load("sample_trial_balance.csv", "Trial Balance")
    return build_statements(add_balances(classify_trial_balance(tb)))


def _ledger(rows):
    df = pd.DataFrame(rows, columns=COLUMNS)
    df["date"] = pd.to_datetime(df["date"])
    return df


def test_classifier_names_and_codes():
    assert classify_account("", "Accounts Payable") == "Payables"
    assert classify_account("", "Accumulated Depreciation") == "Non-current Assets"
    assert classify_account("", "Depreciation Expense") == "Operating Expenses"
    assert classify_account("", "Short-term Borrowings") == "Other Current Liabilities"
    assert classify_account("", "Sales Revenue") == "Revenue"
    assert classify_account("", "Prepaid Expenses") == "Other Current Assets"
    assert classify_account("", "Cash at Bank") == "Cash"
    assert classify_account("4100", "Widgets") == "Revenue"


def test_sample_statements():
    s = _statements()
    assert s["total_assets"] == pytest.approx(33_350_000)
    assert s["total_liabilities"] == pytest.approx(15_600_000)
    assert s["net_profit"] == pytest.approx(3_250_000)
    assert s["total_equity"] == pytest.approx(17_750_000)
    assert s["equation_difference"] == 0


def test_sample_ratios():
    ratios = {r["name"]: r["value"] for r in calculate_ratios(_statements())}
    assert ratios["Current Ratio"] == pytest.approx(2.140625)
    assert ratios["Quick Ratio"] == pytest.approx(11_050_000 / 9_600_000)
    assert ratios["Working Capital"] == pytest.approx(10_950_000)
    assert ratios["Gross Profit Margin"] == pytest.approx(0.30)
    assert ratios["Debt-to-Equity"] == pytest.approx(15_600_000 / 17_750_000)


def test_zero_denominator_gives_none():
    df = pd.DataFrame({"debit": [100.0], "credit": [0.0], "category": ["Cash"]})
    ratios = {r["name"]: r["value"] for r in calculate_ratios(build_statements(add_balances(df)))}
    assert ratios["Current Ratio"] is None
    assert ratios["Gross Profit Margin"] is None


def test_break_even():
    result = break_even(_statements())
    assert result["break_even_revenue"] == pytest.approx(9_350_000 / 0.3)
    assert break_even_units(100_000, 50, 30) == 5000
    assert break_even_units(100_000, 30, 50) is None


def test_sample_ledger_exceptions():
    items = run_all_tests(_load("sample_general_ledger.csv", "General Ledger"))
    tests = [i.test for i in items]
    assert tests.count("Exact duplicate") == 1
    for expected in ("Statistical outlier", "Unusual journal entry", "Round-number analysis",
                     "Unusual timing", "Missing reference"):
        assert expected in tests
    duplicate = next(i for i in items if i.test == "Exact duplicate")
    assert "PAY-2002" in duplicate.references
    assert duplicate.severity == "High"
    assert all(i.review_status == "Pending Review" for i in items)


def test_near_duplicate_found():
    rows = [
        ("2025-07-02", "INV-1", "Purchase", "Inventory", "Karim Traders", 12345, 0),
        ("2025-07-04", "INV-2", "Purchase", "Inventory", "Karim Trader", 12345, 0),
    ]
    assert [i.test for i in run_all_tests(_ledger(rows))] == ["Near-duplicate"]


def test_clean_data_has_no_exceptions():
    rows = [
        ("2025-07-02", "INV-1", "Purchase", "Inventory", "Karim Traders", 12345, 0),
        ("2025-07-09", "INV-2", "Purchase", "Inventory", "Noor Packaging", 67891, 0),
    ]
    assert run_all_tests(_ledger(rows)) == []
