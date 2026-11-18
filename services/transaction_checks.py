"""Transaction checks. Plain rules and statistics.
An exception is something to investigate. It is NOT proof of fraud."""
import re
from dataclasses import dataclass
from difflib import SequenceMatcher

import numpy as np
import pandas as pd
from pydantic import BaseModel

from services.account_classifier import ledger_account_group

SEVERITY_ORDER = {"High": 0, "Medium": 1, "Low": 2}
MANUAL_JOURNAL = re.compile(r"^(JV|JE|ADJ|MJ)[\-/ _]?\d")
ADJUSTMENT_WORDS = ("adjust", "correction", "reversal", "write off", "write-off", "writeoff", "reclass", "suspense")
SUSPENSE_ACCOUNTS = ("miscellaneous", "suspense", "sundry")


class ExceptionItem(BaseModel):
    exception_id: str = ""
    test: str
    severity: str
    title: str
    references: str
    method: str
    explanation: str
    evidence: str
    review_status: str = "Pending Review"


@dataclass
class RuleSettings:
    large_amount: float = 1_000_000
    round_unit: int = 100_000
    round_min: float = 500_000
    fuzzy_days: int = 7
    vendor_similarity: float = 0.85
    amount_tolerance: float = 0.01
    outlier_multiplier: float = 1.5
    outlier_min_rows: int = 8


# ---------- helpers ----------

def _prepare(tx: pd.DataFrame) -> pd.DataFrame:
    df = tx.copy().reset_index(drop=True)
    df["line"] = df.index + 1
    for col in ("reference", "description", "account", "vendor"):
        df[col] = df[col].fillna("").astype(str).str.strip()
    df["debit"] = pd.to_numeric(df["debit"], errors="coerce").fillna(0.0)
    df["credit"] = pd.to_numeric(df["credit"], errors="coerce").fillna(0.0)
    df["amount"] = df[["debit", "credit"]].abs().max(axis=1)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df[df["date"].notna()].copy()
    if df.empty:
        df["exact_group"] = pd.Series(dtype="int64")
        return df
    key = ["date", "reference", "account", "vendor", "debit", "credit"]
    size = df.groupby(key)["line"].transform("size")
    group_id = df.groupby(key).ngroup()
    df["exact_group"] = np.where(size > 1, group_id, -1)
    return df


def _describe(r) -> str:
    return (f"Line {r.line}: {r.date:%d %b %Y}, {r.reference or 'no reference'}, "
            f"{r.account}, {r.vendor or 'no vendor'}, PKR {r.amount:,.0f}")


def _refs(rows, limit=15) -> str:
    names = [f"{r.reference or 'no reference'} (line {r.line})" for r in rows]
    text = "; ".join(names[:limit])
    return text + (f"; and {len(names) - limit} more" if len(names) > limit else "")


def _evidence(rows, limit=10) -> str:
    lines = [_describe(r) for r in rows[:limit]]
    if len(rows) > limit:
        lines.append(f"... and {len(rows) - limit} more transactions.")
    return "\n".join(lines)


def _clean_vendor(name: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", name.lower()).strip()


# ---------- the checks ----------

def check_exact_duplicates(df):
    items = []
    for _, group in df[df["exact_group"] >= 0].groupby("exact_group"):
        rows = list(group.itertuples())
        first = rows[0]
        items.append(ExceptionItem(
            test="Exact duplicate", severity="High", title="Possible duplicate entry",
            references=_refs(rows),
            method="Lines that are identical in date, reference, account, vendor and amount.",
            explanation=(f"{len(rows)} ledger lines are identical (PKR {first.amount:,.0f}, "
                         f"{first.vendor or 'no vendor'}). This may be a double posting or double payment, "
                         "or a legitimately repeated item. Check the supporting documents."),
            evidence=_evidence(rows),
        ))
    return items


def check_near_duplicates(df, cfg):
    items = []
    for account, group in df.groupby("account"):
        rows = list(group.sort_values(["date", "line"]).itertuples())
        for i, a in enumerate(rows):
            if not a.vendor or a.amount <= 0:
                continue
            for b in rows[i + 1:]:
                days = (b.date - a.date).days
                if days > cfg.fuzzy_days:
                    break
                if not b.vendor or (a.exact_group >= 0 and a.exact_group == b.exact_group):
                    continue
                if (a.debit > 0) != (b.debit > 0):
                    continue
                if abs(a.amount - b.amount) > a.amount * cfg.amount_tolerance:
                    continue
                similarity = SequenceMatcher(None, _clean_vendor(a.vendor), _clean_vendor(b.vendor)).ratio()
                if similarity < cfg.vendor_similarity:
                    continue
                pair = [a, b]
                items.append(ExceptionItem(
                    test="Near-duplicate", severity="Medium",
                    title="Similar transactions close together",
                    references=_refs(pair),
                    method=(f"Same account, similar vendor name (at least {cfg.vendor_similarity:.0%} match), "
                            f"amount within {cfg.amount_tolerance:.0%}, dates within {cfg.fuzzy_days} days."),
                    explanation=(f"Two lines in '{account}' have almost the same amount "
                                 f"(PKR {a.amount:,.0f}) and a similar vendor ('{a.vendor}' and '{b.vendor}', "
                                 f"{similarity:.0%} match), {days} day(s) apart. They may be the same invoice "
                                 "entered twice."),
                    evidence=_evidence(pair),
                ))
    return items


def check_outliers(df, cfg):
    items = []
    work = df.copy()
    work["group"] = work["account"].map(ledger_account_group)
    for group, part in work.groupby("group"):
        if len(part) < cfg.outlier_min_rows:
            continue
        q1, q3 = np.percentile(part["amount"], [25, 75])
        spread = q3 - q1
        if spread <= 0:
            continue
        upper = q3 + cfg.outlier_multiplier * spread
        for r in part[part["amount"] > upper].itertuples():
            severity = "High" if r.amount >= cfg.large_amount else "Medium"
            items.append(ExceptionItem(
                test="Statistical outlier", severity=severity,
                title="Amount much larger than usual",
                references=_refs([r]),
                method=(f"IQR rule on {group.lower()} accounts: amounts above the 75th percentile plus "
                        f"{cfg.outlier_multiplier} x the interquartile range."),
                explanation=(f"PKR {r.amount:,.0f} is far above the normal range for {group.lower()} "
                             f"transactions in this ledger (upper limit about PKR {upper:,.0f})."),
                evidence=_describe(r),
            ))
    return items


def check_unusual_journals(df, cfg):
    items = []
    for r in df.itertuples():
        reasons = []
        if MANUAL_JOURNAL.match(r.reference.upper()):
            reasons.append(f"manual journal reference ({r.reference})")
        if any(word in r.description.lower() for word in ADJUSTMENT_WORDS):
            reasons.append("description mentions an adjustment, correction or reversal")
        if any(word in r.account.lower() for word in SUSPENSE_ACCOUNTS):
            reasons.append("posted to a miscellaneous or suspense account")
        if not reasons:
            continue
        severity = "High" if r.amount >= cfg.large_amount else "Medium"
        items.append(ExceptionItem(
            test="Unusual journal entry", severity=severity,
            title="Manual or adjusting journal entry",
            references=_refs([r]),
            method="Rules: manual journal reference (JV/JE/ADJ), adjustment wording, miscellaneous or suspense account.",
            explanation="This entry matches: " + "; ".join(reasons) + ". Such entries are not part of normal "
                        "transaction flow, so check who approved it and why it was needed.",
            evidence=_describe(r),
        ))
    return items


def check_round_numbers(df, cfg):
    if cfg.round_unit <= 0:
        return []
    paisa = (df["amount"] * 100).round().astype("int64")
    mask = (df["amount"] >= cfg.round_min) & (paisa % (int(cfg.round_unit) * 100) == 0)
    rows = list(df[mask].itertuples())
    if not rows:
        return []
    share = len(rows) / len(df)
    return [ExceptionItem(
        test="Round-number analysis", severity="Low",
        title="Large round-amount transactions",
        references=_refs(rows),
        method=(f"Amounts of at least PKR {cfg.round_min:,.0f} that are exact multiples of "
                f"PKR {cfg.round_unit:,.0f}."),
        explanation=(f"{len(rows)} of {len(df)} transactions ({share:.0%}) are large round amounts. Real "
                     "invoices are rarely perfectly round, though contracts and fixed fees can be. "
                     "Review a sample against the documents."),
        evidence=_evidence(rows),
    )]


def check_timing(df, cfg):
    items = []
    weekend = list(df[df["date"].dt.dayofweek >= 5].itertuples())
    if weekend:
        big = any(r.amount >= cfg.large_amount for r in weekend)
        items.append(ExceptionItem(
            test="Unusual timing", severity="Medium" if big else "Low",
            title="Transactions dated on a weekend",
            references=_refs(weekend),
            method="Transaction dates that fall on a Saturday or Sunday.",
            explanation=(f"{len(weekend)} transaction(s) are dated on a weekend. Some businesses do work on "
                         "weekends, so check whether this is normal for this company."),
            evidence=_evidence(weekend),
        ))
    year_end = list(df[(df["date"].dt.month == 6) & (df["date"].dt.day >= 28)
                       & (df["amount"] >= cfg.large_amount)].itertuples())
    if year_end:
        items.append(ExceptionItem(
            test="Unusual timing", severity="Medium",
            title="Large transactions at fiscal year-end",
            references=_refs(year_end),
            method="Amounts at or above the large-amount limit dated 28-30 June (end of the Pakistani fiscal year).",
            explanation=("Large entries just before year-end can be recorded in the wrong period (cut-off). "
                         "Check delivery or service dates against the supporting documents."),
            evidence=_evidence(year_end),
        ))
    return items


def check_missing_references(df, cfg):
    rows = list(df[df["reference"] == ""].itertuples())
    if not rows:
        return []
    big = any(r.amount >= cfg.large_amount for r in rows)
    return [ExceptionItem(
        test="Missing reference", severity="High" if big else "Medium",
        title="Transactions without a reference number",
        references=_refs(rows),
        method="Ledger lines where the reference or voucher number is blank.",
        explanation=(f"{len(rows)} transaction(s) have no reference number, so they cannot be traced to an "
                     "invoice or voucher. Ask management for the supporting documents."),
        evidence=_evidence(rows),
    )]


# ---------- run everything ----------

def run_all_tests(tx: pd.DataFrame, settings: RuleSettings | None = None) -> list:
    if tx is None or tx.empty:
        return []
    cfg = settings or RuleSettings()
    df = _prepare(tx)
    if df.empty:
        return []

    items = []
    items += check_exact_duplicates(df)
    items += check_near_duplicates(df, cfg)
    items += check_outliers(df, cfg)
    items += check_unusual_journals(df, cfg)
    items += check_round_numbers(df, cfg)
    items += check_timing(df, cfg)
    items += check_missing_references(df, cfg)

    items.sort(key=lambda item: SEVERITY_ORDER[item.severity])
    for number, item in enumerate(items, start=1):
        item.exception_id = f"EX-{number:03d}"
    return items
