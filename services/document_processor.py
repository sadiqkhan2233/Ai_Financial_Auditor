"""Reads uploaded files and turns them into clean, standard tables."""
import io
import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

TB_COLUMNS = ["account_code", "account_name", "debit", "credit"]
GL_COLUMNS = ["date", "reference", "description", "account", "vendor", "debit", "credit"]

TB_SYNONYMS = {
    "account_code": ["account code", "code", "acc code", "a/c code", "account no", "account number"],
    "account_name": ["account name", "account", "account title", "particulars", "name"],
    "debit": ["debit", "debits", "dr", "debit amount", "debit pkr"],
    "credit": ["credit", "credits", "cr", "credit amount", "credit pkr"],
}
GL_SYNONYMS = {
    "date": ["date", "posting date", "txn date", "transaction date", "voucher date"],
    "reference": ["reference", "ref", "ref no", "voucher no", "voucher", "invoice no", "document no", "doc no"],
    "description": ["description", "narration", "details", "particulars"],
    "account": ["account", "account name", "gl account", "account title"],
    "vendor": ["vendor", "supplier", "party", "payee", "customer", "customer name", "vendor name"],
    "debit": ["debit", "debits", "dr", "debit amount", "debit pkr"],
    "credit": ["credit", "credits", "cr", "credit amount", "credit pkr"],
}


@dataclass
class ValidationReport:
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    info: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not self.errors


# ---------- reading files ----------

def read_table(filename: str, data: bytes, sheet=None) -> pd.DataFrame:
    """Read a CSV or Excel file. Everything is read as text and cleaned later."""
    ext = Path(filename).suffix.lower()
    if ext == ".csv":
        try:
            return pd.read_csv(io.BytesIO(data), dtype=str, keep_default_na=False)
        except UnicodeDecodeError:
            return pd.read_csv(io.BytesIO(data), dtype=str, keep_default_na=False, encoding="latin-1")
    if ext == ".xlsx":
        return pd.read_excel(
            io.BytesIO(data), sheet_name=sheet or 0, dtype=str,
            keep_default_na=False, engine="openpyxl",
        )
    raise ValueError("Unsupported file type for tables.")


def get_sheet_names(data: bytes) -> list:
    return pd.ExcelFile(io.BytesIO(data), engine="openpyxl").sheet_names


def extract_pdf(data: bytes):
    """Returns (page_count, text, tables). Tables is a list of (page_number, DataFrame)."""
    import fitz  # PyMuPDF

    texts, tables = [], []
    with fitz.open(stream=data, filetype="pdf") as doc:
        page_count = doc.page_count
        for number, page in enumerate(doc, start=1):
            texts.append(page.get_text())
            try:
                for table in page.find_tables().tables:
                    tables.append((number, table.to_pandas()))
            except Exception:
                pass  # table detection is a bonus, not required
    return page_count, "\n".join(texts), tables


# ---------- cleaning helpers ----------

def _norm(text) -> str:
    text = str(text).lower().replace("_", " ")
    text = re.sub(r"[^a-z0-9/ ]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def rename_columns(df: pd.DataFrame, synonyms: dict) -> pd.DataFrame:
    lookup = {}
    for standard, names in synonyms.items():
        lookup[_norm(standard)] = standard
        for name in names:
            lookup[_norm(name)] = standard
    mapping, used = {}, set()
    for col in df.columns:
        standard = lookup.get(_norm(col))
        if standard and standard not in used:
            mapping[col] = standard
            used.add(standard)
    return df.rename(columns=mapping)


def _clean_text(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip().replace({"nan": "", "None": ""})


def _drop_empty_rows(df: pd.DataFrame) -> pd.DataFrame:
    blank = df.fillna("").astype(str).apply(lambda col: col.str.strip() == "")
    return df[~blank.all(axis=1)]


def clean_amount(series: pd.Series):
    """Turns text like '1,250,000' or '(500)' into numbers. Returns (numbers, bad_mask)."""
    text = series.fillna("").astype(str).str.strip()
    blank = text.isin(["", "nan", "None", "NaN"])
    negative = text.str.startswith("(") & text.str.endswith(")")
    num = pd.to_numeric(text.str.replace(r"[^\d.\-]", "", regex=True), errors="coerce")
    num = num.where(~negative, -num.abs())
    bad = num.isna() & ~blank
    num = num.where(~blank, 0.0).fillna(0.0)
    return num, bad


def parse_dates(series: pd.Series) -> pd.Series:
    """Understands 2025-07-02 first, then day-first dates like 02/07/2025."""
    text = series.fillna("").astype(str).str.strip()
    text = text.str.replace(r"\s+00:00:00$", "", regex=True)
    out = pd.to_datetime(text, format="%Y-%m-%d", errors="coerce")
    missing = out.isna()
    if missing.any():
        out[missing] = pd.to_datetime(text[missing], dayfirst=True, format="mixed", errors="coerce")
    return out


def _rows(mask: pd.Series) -> str:
    """File row numbers (header is row 1) for the first few True values."""
    numbers = [str(i + 2) for i in mask[mask].index[:5]]
    return ", ".join(numbers) + (", ..." if int(mask.sum()) > 5 else "")


# ---------- main entry point ----------

def process_table(raw: pd.DataFrame, doc_type: str):
    """Cleans a table and checks it. Returns (clean_dataframe, ValidationReport)."""
    report = ValidationReport()
    if raw is None or raw.empty:
        report.errors.append("The file has no data rows.")
        return pd.DataFrame(), report
    if doc_type == "Trial Balance":
        return _process_trial_balance(raw, report)
    return _process_ledger(raw, report)


def _check_amounts(df: pd.DataFrame, report: ValidationReport) -> None:
    for col in ("debit", "credit"):
        df[col], bad = clean_amount(df[col])
        if bad.any():
            report.errors.append(
                f"{int(bad.sum())} value(s) in '{col}' are not valid numbers (file rows: {_rows(bad)})."
            )
    if ((df["debit"] < 0) | (df["credit"] < 0)).any():
        report.warnings.append("Some debit or credit amounts are negative. Please check them.")
    if ((df["debit"] > 0) & (df["credit"] > 0)).any():
        report.warnings.append("Some rows have both a debit and a credit amount.")


def _process_trial_balance(raw: pd.DataFrame, report: ValidationReport):
    df = rename_columns(raw.copy(), TB_SYNONYMS)
    missing = [c for c in ("account_name", "debit", "credit") if c not in df.columns]
    if missing:
        report.errors.append(
            f"Missing required column(s): {', '.join(missing)}. "
            f"Columns found in your file: {', '.join(map(str, raw.columns))}."
        )
        return pd.DataFrame(), report
    if "account_code" not in df.columns:
        df["account_code"] = ""

    df = _drop_empty_rows(df[TB_COLUMNS].copy())
    df["account_name"] = _clean_text(df["account_name"])
    df["account_code"] = _clean_text(df["account_code"]).str.replace(r"\.0$", "", regex=True)

    is_total = df["account_name"].str.lower().isin(["total", "totals", "grand total"])
    if is_total.any():
        report.info.append("A 'Total' row was found and ignored so it is not counted twice.")
        df = df[~is_total]
    if df.empty:
        report.errors.append("No account rows were found.")
        return pd.DataFrame(), report

    _check_amounts(df, report)

    no_name = df["account_name"] == ""
    if no_name.any():
        report.warnings.append(f"{int(no_name.sum())} row(s) have no account name.")
    names = df.loc[~no_name, "account_name"]
    repeated = names[names.duplicated(keep=False)].unique()
    if len(repeated):
        report.warnings.append(f"Repeated account name(s): {', '.join(repeated[:5])}.")

    total_debit = round(float(df["debit"].sum()), 2)
    total_credit = round(float(df["credit"].sum()), 2)
    difference = round(total_debit - total_credit, 2)
    report.stats = {
        "rows": len(df), "total_debit": total_debit,
        "total_credit": total_credit, "difference": difference,
    }
    if abs(difference) > 0.01:
        report.errors.append(
            f"The trial balance does not balance: debits {total_debit:,.2f} and "
            f"credits {total_credit:,.2f} (difference {difference:,.2f})."
        )
    else:
        report.info.append("Total debits equal total credits. The trial balance is balanced.")
    return df.reset_index(drop=True), report


def _process_ledger(raw: pd.DataFrame, report: ValidationReport):
    df = rename_columns(raw.copy(), GL_SYNONYMS)
    missing = [c for c in ("date", "account", "debit", "credit") if c not in df.columns]
    if missing:
        report.errors.append(
            f"Missing required column(s): {', '.join(missing)}. "
            f"Columns found in your file: {', '.join(map(str, raw.columns))}."
        )
        return pd.DataFrame(), report

    has_reference = "reference" in df.columns
    if not has_reference:
        report.warnings.append("No reference column was found, so reference checks are not possible.")
    for col in ("reference", "description", "vendor"):
        if col not in df.columns:
            df[col] = ""

    df = _drop_empty_rows(df[GL_COLUMNS].copy())
    if df.empty:
        report.errors.append("No transaction rows were found.")
        return pd.DataFrame(), report

    for col in ("reference", "description", "account", "vendor"):
        df[col] = _clean_text(df[col])

    df["date"] = parse_dates(df["date"])
    bad_dates = df["date"].isna()
    if bad_dates.any():
        report.errors.append(
            f"{int(bad_dates.sum())} row(s) have a missing or invalid date (file rows: {_rows(bad_dates)})."
        )

    _check_amounts(df, report)

    no_amount = (df["debit"] == 0) & (df["credit"] == 0)
    if no_amount.any():
        report.warnings.append(f"{int(no_amount.sum())} row(s) have no amount (file rows: {_rows(no_amount)}).")

    if has_reference:
        no_ref = df["reference"] == ""
        if no_ref.any():
            report.warnings.append(
                f"{int(no_ref.sum())} row(s) have no reference number (file rows: {_rows(no_ref)}). "
                "They will be flagged for review in transaction testing."
            )

    valid_dates = df["date"].dropna()
    if not valid_dates.empty:
        report.info.append(
            f"Transactions run from {valid_dates.min():%d %b %Y} to {valid_dates.max():%d %b %Y}."
        )
    report.stats = {
        "rows": len(df),
        "total_debit": round(float(df["debit"].sum()), 2),
        "total_credit": round(float(df["credit"].sum()), 2),
    }
    return df.reset_index(drop=True), report
