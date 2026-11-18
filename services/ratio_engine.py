"""All financial calculations. Plain maths - no AI is used here."""
import math

import numpy as np
import pandas as pd

from services.account_classifier import CREDIT_NATURE, DEBIT_NATURE, ledger_account_group


def safe_div(top, bottom):
    if bottom is None or abs(bottom) < 1e-9:
        return None
    return top / bottom


def add_balances(df: pd.DataFrame) -> pd.DataFrame:
    """Adds a 'balance' column: positive for the normal side of each group."""
    out = df.copy()
    net = out["debit"].astype(float) - out["credit"].astype(float)
    out["balance"] = np.select(
        [out["category"].isin(DEBIT_NATURE), out["category"].isin(CREDIT_NATURE)],
        [net, -net],
        default=0.0,
    )
    return out


def build_statements(df: pd.DataFrame) -> dict:
    """Builds balance sheet and profit figures from the classified trial balance."""
    totals = df.groupby("category")["balance"].sum()

    def get(category):
        return float(totals.get(category, 0.0))

    cash, receivables, inventory = get("Cash"), get("Receivables"), get("Inventory")
    other_current_assets = get("Other Current Assets")
    current_assets = cash + receivables + inventory + other_current_assets
    non_current_assets = get("Non-current Assets")
    total_assets = current_assets + non_current_assets

    current_liabilities = get("Payables") + get("Other Current Liabilities")
    non_current_liabilities = get("Non-current Liabilities")
    total_liabilities = current_liabilities + non_current_liabilities

    revenue, cost_of_sales = get("Revenue"), get("Cost of Sales")
    gross_profit = revenue - cost_of_sales
    operating_expenses, other_income = get("Operating Expenses"), get("Other Income")
    finance_cost, tax_expense = get("Finance Cost"), get("Tax Expense")
    net_profit = gross_profit - operating_expenses + other_income - finance_cost - tax_expense

    # A trial balance is before closing entries, so this year's profit is added to equity.
    equity_accounts = get("Equity")
    total_equity = equity_accounts + net_profit

    return {
        "cash": cash, "receivables": receivables, "inventory": inventory,
        "other_current_assets": other_current_assets, "current_assets": current_assets,
        "non_current_assets": non_current_assets, "total_assets": total_assets,
        "current_liabilities": current_liabilities, "non_current_liabilities": non_current_liabilities,
        "total_liabilities": total_liabilities,
        "revenue": revenue, "cost_of_sales": cost_of_sales, "gross_profit": gross_profit,
        "operating_expenses": operating_expenses, "other_income": other_income,
        "finance_cost": finance_cost, "tax_expense": tax_expense, "net_profit": net_profit,
        "equity_accounts": equity_accounts, "total_equity": total_equity,
        "equation_difference": round(total_assets - total_liabilities - total_equity, 2),
    }


def _ratio(group, name, value, kind, formula, meaning):
    return {"group": group, "name": name, "value": value, "kind": kind,
            "formula": formula, "meaning": meaning}


def calculate_ratios(s: dict) -> list:
    return [
        _ratio("Liquidity", "Current Ratio", safe_div(s["current_assets"], s["current_liabilities"]), "x",
               "Current assets / Current liabilities",
               "Can short-term assets cover short-term debts?"),
        _ratio("Liquidity", "Quick Ratio", safe_div(s["current_assets"] - s["inventory"], s["current_liabilities"]), "x",
               "(Current assets - Inventory) / Current liabilities",
               "Same test, without relying on selling inventory."),
        _ratio("Liquidity", "Working Capital", s["current_assets"] - s["current_liabilities"], "amount",
               "Current assets - Current liabilities",
               "Short-term resources left after paying short-term debts."),
        _ratio("Profitability", "Gross Profit Margin", safe_div(s["gross_profit"], s["revenue"]), "percent",
               "(Revenue - Cost of sales) / Revenue",
               "Profit kept from each rupee of sales before running costs."),
        _ratio("Profitability", "Net Profit Margin", safe_div(s["net_profit"], s["revenue"]), "percent",
               "Net profit / Revenue",
               "Profit kept from each rupee of sales after all costs."),
        _ratio("Profitability", "Return on Assets (ROA)", safe_div(s["net_profit"], s["total_assets"]), "percent",
               "Net profit / Total assets",
               "Profit earned from the assets the company owns."),
        _ratio("Profitability", "Return on Equity (ROE)", safe_div(s["net_profit"], s["total_equity"]), "percent",
               "Net profit / Total equity",
               "Profit earned on the owners' investment."),
        _ratio("Solvency", "Debt-to-Equity", safe_div(s["total_liabilities"], s["total_equity"]), "x",
               "Total liabilities / Total equity",
               "How much of the business is funded by debt compared with owners' money."),
        _ratio("Efficiency", "Inventory Turnover", safe_div(s["cost_of_sales"], s["inventory"]), "x",
               "Cost of sales / Inventory",
               "How many times inventory is sold and replaced in the period."),
        _ratio("Efficiency", "Receivables Turnover", safe_div(s["revenue"], s["receivables"]), "x",
               "Revenue / Receivables",
               "How quickly customers pay (assumes sales are on credit)."),
    ]


def format_value(value, kind) -> str:
    if value is None:
        return "n/a"
    if kind == "percent":
        return f"{value * 100:.1f}%"
    if kind == "amount":
        return f"PKR {value:,.0f}"
    return f"{value:.2f}"


def review_points(s: dict) -> list:
    points = []
    if abs(s["equation_difference"]) > 1:
        points.append("Assets do not equal liabilities plus equity. Check that every account is in the right group.")
    if s["revenue"] <= 0:
        points.append("No revenue was found, so margins and turnover ratios cannot be calculated.")
    current_ratio = safe_div(s["current_assets"], s["current_liabilities"])
    if current_ratio is not None and current_ratio < 1:
        points.append("The current ratio is below 1: short-term debts are larger than short-term assets.")
    if s["net_profit"] < 0:
        points.append("The company shows a net loss for the period. Consider the effect on the going-concern assessment.")
    if s["total_equity"] <= 0:
        points.append("Total equity is zero or negative.")
    return points


def break_even(s: dict):
    """Estimate: cost of sales varies with sales; operating expenses and finance cost are fixed."""
    revenue = s["revenue"]
    if revenue <= 0:
        return None
    variable = s["cost_of_sales"]
    fixed = s["operating_expenses"] + s["finance_cost"]
    margin_ratio = (revenue - variable) / revenue
    if margin_ratio <= 0:
        return None
    break_even_revenue = fixed / margin_ratio
    return {
        "fixed_costs": fixed,
        "variable_costs": variable,
        "contribution_margin_ratio": margin_ratio,
        "break_even_revenue": break_even_revenue,
        "margin_of_safety": (revenue - break_even_revenue) / revenue,
    }


def break_even_units(fixed_costs: float, price: float, variable_cost: float):
    margin = price - variable_cost
    if margin <= 0:
        return None
    return math.ceil(fixed_costs / margin)


def monthly_trend(tx: pd.DataFrame) -> pd.DataFrame:
    """Monthly revenue and expenses from the general ledger."""
    df = tx.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df[df["date"].notna()].copy()
    df["group"] = df["account"].fillna("").map(ledger_account_group)
    df = df[df["group"].isin(["Revenue", "Expense"])].copy()
    if df.empty:
        return pd.DataFrame(columns=["month", "Revenue", "Expense", "Net"])

    df["amount"] = np.where(df["group"] == "Revenue", df["credit"] - df["debit"], df["debit"] - df["credit"])
    df["month"] = df["date"].dt.to_period("M").dt.to_timestamp()
    table = df.pivot_table(index="month", columns="group", values="amount", aggfunc="sum", fill_value=0.0)
    for col in ("Revenue", "Expense"):
        if col not in table.columns:
            table[col] = 0.0
    months = pd.date_range(table.index.min(), table.index.max(), freq="MS")
    table = table.reindex(months, fill_value=0.0)
    out = table[["Revenue", "Expense"]].copy()
    out["Net"] = out["Revenue"] - out["Expense"]
    return out.rename_axis("month").reset_index()


def account_totals(tx: pd.DataFrame) -> pd.DataFrame:
    out = (
        tx.groupby("account")
        .agg(Lines=("account", "size"), Debit=("debit", "sum"), Credit=("credit", "sum"))
        .reset_index()
        .rename(columns={"account": "Account"})
    )
    out["Total"] = out["Debit"] + out["Credit"]
    out = out.sort_values("Total", ascending=False).drop(columns="Total")
    return out.round(0)
