"""Puts trial balance accounts into groups so ratios can be calculated."""
import re
from functools import lru_cache

import pandas as pd

CATEGORIES = [
    "Cash", "Receivables", "Inventory", "Other Current Assets", "Non-current Assets",
    "Payables", "Other Current Liabilities", "Non-current Liabilities",
    "Equity",
    "Revenue", "Other Income", "Cost of Sales", "Operating Expenses", "Finance Cost", "Tax Expense",
    "Unclassified",
]

# Debit-balance groups (assets and expenses) and credit-balance groups (liabilities, equity, income)
DEBIT_NATURE = {
    "Cash", "Receivables", "Inventory", "Other Current Assets", "Non-current Assets",
    "Cost of Sales", "Operating Expenses", "Finance Cost", "Tax Expense",
}
CREDIT_NATURE = {
    "Payables", "Other Current Liabilities", "Non-current Liabilities",
    "Equity", "Revenue", "Other Income",
}

# The order matters: the first match wins.
RULES = [
    ("Non-current Assets", ["accumulated depreciation", "accumulated amortization", "accumulated amortisation"]),
    ("Other Current Liabilities", ["short-term", "short term", "current portion", "accrued", "tax payable",
                                   "sales tax", "withholding", "unearned", "customer advance",
                                   "advance from", "overdraft", "running finance"]),
    ("Non-current Liabilities", ["long-term", "long term", "term loan", "term finance", "lease liabilit",
                                 "deferred tax", "debenture", "sukuk", "borrowing", "bank loan"]),
    ("Payables", ["payable", "creditors"]),
    ("Equity", ["share capital", "paid-up", "paid up", "retained", "reserve", "surplus", "owner"]),
    ("Cost of Sales", ["cost of goods", "cost of sales", "cost of revenue", "cogs"]),
    ("Finance Cost", ["finance cost", "interest expense", "markup", "mark-up", "bank charges"]),
    ("Tax Expense", ["tax expense", "taxation"]),
    ("Other Income", ["other income", "interest income", "dividend income", "rental income",
                      "miscellaneous income", "service income", "fee income", "gain on"]),
    ("Other Current Assets", ["prepaid", "advance", "deposit"]),
    ("Operating Expenses", ["expense", "salar", "wage", "rent", "utilit", "depreciation", "amortization",
                            "amortisation", "fee", "repair", "travel", "insurance", "telephone",
                            "stationery", "advertis", "commission", "electricity", "maintenance",
                            "freight", "bad debt", "marketing"]),
    ("Revenue", ["revenue", "turnover", "sales"]),
    ("Cash", ["cash", "bank"]),
    ("Receivables", ["receivable", "debtors"]),
    ("Inventory", ["inventory", "stock", "stores"]),
    ("Non-current Assets", ["property", "plant", "equipment", "building", "land", "vehicle", "furniture",
                            "machinery", "computer", "intangible", "goodwill", "capital work", "investment"]),
]


def _category_from_code(code: str) -> str:
    """Backup guess from the account number (usual 1xxx-6xxx layout)."""
    match = re.match(r"\d+", str(code).strip())
    if not match:
        return "Unclassified"
    number = int(match.group())
    first = int(str(number)[0])
    if first == 1:
        return "Non-current Assets" if number >= 1500 else "Other Current Assets"
    if first == 2:
        return "Non-current Liabilities" if number >= 2400 else "Other Current Liabilities"
    if first == 3:
        return "Equity"
    if first == 4:
        return "Revenue"
    if first == 5:
        return "Cost of Sales"
    if first == 6:
        return "Operating Expenses"
    return "Unclassified"


def classify_account(code, name) -> str:
    text = str(name).lower()
    for category, words in RULES:
        for word in words:
            if re.search(r"\b" + re.escape(word), text):
                return category
    return _category_from_code(code)


def classify_trial_balance(tb: pd.DataFrame) -> pd.DataFrame:
    out = tb.copy()
    out["category"] = [classify_account(c, n) for c, n in zip(out["account_code"], out["account_name"])]
    return out


@lru_cache(maxsize=2048)
def ledger_account_group(name: str) -> str:
    """Simple grouping for ledger accounts: Revenue, Expense or Other."""
    category = classify_account("", name)
    if category in ("Revenue", "Other Income"):
        return "Revenue"
    if category in ("Cost of Sales", "Operating Expenses", "Finance Cost", "Tax Expense"):
        return "Expense"
    return "Other"
