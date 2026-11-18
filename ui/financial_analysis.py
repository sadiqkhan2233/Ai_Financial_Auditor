import pandas as pd
import plotly.express as px
import streamlit as st

from services.account_classifier import CATEGORIES, classify_trial_balance
from services.data_access import load_transactions, load_trial_balance
from services.ratio_engine import (
    account_totals, add_balances, break_even, break_even_units, build_statements,
    calculate_ratios, format_value, monthly_trend, review_points,
)
from ui.common import pick_engagement


def _money(value) -> str:
    return f"PKR {value:,.0f}"


def show_financial_analysis():
    st.title("📈 Financial Analysis")
    st.caption("Every number here comes from fixed formulas, not from the AI.")

    engagement_id = pick_engagement()
    if engagement_id is None:
        return
    trial_balance = load_trial_balance(engagement_id)
    if trial_balance.empty:
        st.warning("No trial balance is saved for this engagement. Upload one in the Document Upload Center.")
        return

    tab_groups, tab_overview, tab_ratios, tab_trends, tab_break = st.tabs(
        ["1. Account groups", "2. Overview", "3. Ratios", "4. Trends", "5. Break-even"]
    )

    with tab_groups:
        st.write("The app guessed a group for each account. **Please check them** and change any that are "
                 "wrong. All results update automatically.")
        edited = st.data_editor(
            classify_trial_balance(trial_balance),
            column_config={
                "category": st.column_config.SelectboxColumn("Category", options=CATEGORIES, required=True)
            },
            disabled=["account_code", "account_name", "debit", "credit"],
            hide_index=True,
            key=f"classification_{engagement_id}",
        )
        if (edited["category"] == "Unclassified").any():
            st.warning("Some accounts are 'Unclassified'. They are left out of the results until you choose a group.")

    statements = build_statements(add_balances(edited))

    with tab_overview:
        cols = st.columns(4)
        cols[0].metric("Total assets", _money(statements["total_assets"]))
        cols[1].metric("Total liabilities", _money(statements["total_liabilities"]))
        cols[2].metric("Total equity", _money(statements["total_equity"]))
        cols[3].metric("Net profit", _money(statements["net_profit"]))
        if abs(statements["equation_difference"]) <= 1:
            st.success("Check passed: assets equal liabilities plus equity.")
        else:
            st.error(f"Assets and (liabilities + equity) differ by {_money(statements['equation_difference'])}.")
        st.caption("Equity = share capital and reserves + this period's profit, because a trial balance is "
                   "prepared before closing entries.")
        for point in review_points(statements):
            st.warning(point)

        position = pd.DataFrame({
            "Item": ["Total assets", "Total liabilities", "Total equity"],
            "PKR": [statements["total_assets"], statements["total_liabilities"], statements["total_equity"]],
        })
        st.plotly_chart(px.bar(position, x="Item", y="PKR", title="Financial position"))
        profit = pd.DataFrame({
            "Item": ["Revenue", "Cost of sales", "Operating expenses", "Finance cost", "Tax", "Net profit"],
            "PKR": [statements["revenue"], statements["cost_of_sales"], statements["operating_expenses"],
                    statements["finance_cost"], statements["tax_expense"], statements["net_profit"]],
        })
        st.plotly_chart(px.bar(profit, x="Item", y="PKR", title="Profit breakdown"))

    with tab_ratios:
        ratios = calculate_ratios(statements)
        for group in ("Liquidity", "Profitability", "Solvency", "Efficiency"):
            st.subheader(group)
            rows = [
                {"Ratio": r["name"], "Value": format_value(r["value"], r["kind"]),
                 "Formula": r["formula"], "What it shows": r["meaning"]}
                for r in ratios if r["group"] == group
            ]
            st.dataframe(pd.DataFrame(rows), hide_index=True)
        st.caption("Ratios use year-end balances from one trial balance (no averages). 'n/a' means the formula "
                   "cannot be calculated, for example because of a zero denominator. Compare ratios with "
                   "the industry before drawing conclusions.")

    with tab_trends:
        ledger = load_transactions(engagement_id)
        if ledger.empty:
            st.info("No general ledger is saved for this engagement.")
        else:
            trend = monthly_trend(ledger)
            if trend.empty:
                st.info("No revenue or expense accounts could be recognised in the ledger.")
            else:
                st.plotly_chart(px.bar(trend, x="month", y=["Revenue", "Expense"], barmode="group",
                                       title="Monthly revenue and expenses (from the ledger)"))
                st.dataframe(trend.round(0), hide_index=True)
            st.subheader("Totals by account")
            st.dataframe(account_totals(ledger), hide_index=True)

    with tab_break:
        result = break_even(statements)
        if result is None:
            st.info("Break-even cannot be estimated. It needs positive sales and a positive margin after cost of sales.")
        else:
            cols = st.columns(3)
            cols[0].metric("Break-even revenue", _money(result["break_even_revenue"]))
            cols[1].metric("Contribution margin", f"{result['contribution_margin_ratio'] * 100:.1f}%")
            cols[2].metric("Margin of safety", f"{result['margin_of_safety'] * 100:.1f}%")
            st.caption("Estimate based on an assumption: cost of sales rises and falls with sales, while operating "
                       "expenses and finance cost are fixed. Real cost behaviour may differ, so review before relying on it.")

        st.subheader("Break-even in units (enter your own figures)")
        c1, c2, c3 = st.columns(3)
        fixed = c1.number_input("Fixed costs (PKR)", min_value=0.0, value=0.0, step=100000.0)
        price = c2.number_input("Selling price per unit (PKR)", min_value=0.0, value=0.0, step=10.0)
        variable = c3.number_input("Variable cost per unit (PKR)", min_value=0.0, value=0.0, step=10.0)
        if price > 0:
            units = break_even_units(fixed, price, variable)
            if units is None:
                st.error("The selling price must be higher than the variable cost per unit.")
            else:
                st.success(f"Break-even point: {units:,} units.")
