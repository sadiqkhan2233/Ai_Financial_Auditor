import pandas as pd
import pytest

from config.settings import BASE_DIR
from services.document_processor import clean_amount, process_table, read_table
from services.file_validation import validate_upload

SAMPLES = BASE_DIR / "data" / "sample_data"


def make_tb(credit_value="500"):
    return pd.DataFrame({
        "Account Code": ["1000", "2000"],
        "Account Name": ["Cash", "Capital"],
        "Debit": ["500", "0"],
        "Credit": ["0", credit_value],
    })


def test_balanced_trial_balance_passes():
    clean, report = process_table(make_tb("500"), "Trial Balance")
    assert report.passed
    assert report.stats["difference"] == 0
    assert len(clean) == 2


def test_unbalanced_trial_balance_fails():
    _, report = process_table(make_tb("450"), "Trial Balance")
    assert not report.passed
    assert any("does not balance" in e for e in report.errors)


def test_total_row_is_ignored():
    df = pd.concat(
        [make_tb("500"), pd.DataFrame({"Account Code": [""], "Account Name": ["Total"],
                                       "Debit": ["500"], "Credit": ["500"]})],
        ignore_index=True,
    )
    clean, report = process_table(df, "Trial Balance")
    assert report.passed
    assert len(clean) == 2


def test_missing_columns_are_reported():
    _, report = process_table(pd.DataFrame({"foo": ["1"]}), "Trial Balance")
    assert not report.passed


def test_amounts_with_commas_and_brackets():
    numbers, bad = clean_amount(pd.Series(["1,250,000", "(500)", "", "abc"]))
    assert numbers.tolist()[:3] == [1250000.0, -500.0, 0.0]
    assert bad.tolist() == [False, False, False, True]


def test_ledger_bad_date_and_missing_reference():
    df = pd.DataFrame({
        "Date": ["2025-07-02", "not a date"],
        "Reference": ["", "R1"],
        "Account": ["Rent Expense", "Rent Expense"],
        "Debit": ["100", "200"],
        "Credit": ["0", "0"],
    })
    _, report = process_table(df, "General Ledger")
    assert not report.passed
    assert any("invalid date" in e for e in report.errors)
    assert any("no reference" in w for w in report.warnings)


def test_upload_rules():
    assert not validate_upload("virus.exe", b"x")[0]
    assert validate_upload("data.csv", b"a,b\n1,2")[0]
    assert not validate_upload("fake.pdf", b"not a pdf")[0]
    assert not validate_upload("empty.csv", b"")[0]


def test_sample_files_work():
    tb_path = SAMPLES / "sample_trial_balance.csv"
    gl_path = SAMPLES / "sample_general_ledger.csv"
    if not tb_path.exists() or not gl_path.exists():
        pytest.skip("Sample files not added yet")
    _, tb_report = process_table(read_table(tb_path.name, tb_path.read_bytes()), "Trial Balance")
    assert tb_report.passed
    _, gl_report = process_table(read_table(gl_path.name, gl_path.read_bytes()), "General Ledger")
    assert gl_report.passed
    assert any("no reference" in w for w in gl_report.warnings)
