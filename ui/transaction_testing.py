import pandas as pd
import streamlit as st

from models.database import log_activity
from services.data_access import load_transactions
from services.findings_service import save_exceptions
from services.transaction_checks import RuleSettings, run_all_tests
from ui.common import pick_engagement

ICONS = {"High": "🔴", "Medium": "🟡", "Low": "🔵"}


def show_transaction_testing():
    st.title("🔎 Transaction Testing")
    st.caption("Each exception is something to investigate. It is not proof of fraud or error.")

    engagement_id = pick_engagement()
    if engagement_id is None:
        return
    ledger = load_transactions(engagement_id)
    if ledger.empty:
        st.warning("No general ledger is saved for this engagement. Upload one in the Document Upload Center.")
        return

    with st.expander("Advanced settings (optional)"):
        large = st.number_input("Large amount (PKR)", min_value=0.0, value=1_000_000.0, step=100_000.0)
        round_unit = st.number_input("Round-number unit (PKR)", min_value=1.0, value=100_000.0, step=10_000.0)
        round_min = st.number_input("Smallest amount for the round-number check (PKR)",
                                    min_value=0.0, value=500_000.0, step=50_000.0)
        days = st.number_input("Days apart for near-duplicates", min_value=1, max_value=60, value=7)

    rules = RuleSettings(large_amount=large, round_unit=int(round_unit),
                         round_min=round_min, fuzzy_days=int(days))
    items = run_all_tests(ledger, rules)

    counts = {level: sum(1 for i in items if i.severity == level) for level in ICONS}
    cols = st.columns(5)
    cols[0].metric("Lines tested", len(ledger))
    cols[1].metric("Exceptions", len(items))
    cols[2].metric("🔴 High", counts["High"])
    cols[3].metric("🟡 Medium", counts["Medium"])
    cols[4].metric("🔵 Low", counts["Low"])

    if not items:
        st.success("No exceptions were found with the current settings.")
    else:
        c1, c2, c3 = st.columns(3)
        severities = c1.multiselect("Severity", list(ICONS), default=list(ICONS))
        test_names = sorted({i.test for i in items})
        chosen_tests = c2.multiselect("Test", test_names, default=test_names)
        search = c3.text_input("Search (reference, vendor, account)")

        shown = [
            i for i in items
            if i.severity in severities and i.test in chosen_tests
            and (not search or search.lower() in (i.references + i.evidence + i.title).lower())
        ]
        if not shown:
            st.info("No exceptions match your filters.")
        else:
            table = pd.DataFrame([
                {"ID": i.exception_id, "Severity": f"{ICONS[i.severity]} {i.severity}", "Test": i.test,
                 "Title": i.title, "References": i.references, "Status": i.review_status}
                for i in shown
            ])
            st.dataframe(table, hide_index=True)

            for item in shown[:25]:
                with st.expander(f"{item.exception_id} · {ICONS[item.severity]} {item.title}"):
                    st.write(f"**Method:** {item.method}")
                    st.write(f"**Explanation:** {item.explanation}")
                    st.text(item.evidence)
                    st.write(f"**Review status:** {item.review_status}")
            if len(shown) > 25:
                st.caption("Details are shown for the first 25 exceptions. The table above lists all of them.")

            full = pd.DataFrame([i.model_dump() for i in shown])
            st.download_button("Download exceptions (CSV)", full.to_csv(index=False).encode("utf-8"),
                               file_name="exceptions.csv", mime="text/csv")

        if st.button("Save exceptions to Audit Findings", type="primary"):
            new, skipped = save_exceptions(engagement_id, items)
            log_activity("exceptions_saved", f"engagement {engagement_id}: {new} new, {skipped} already saved")
            st.success(f"Saved {new} new finding(s). {skipped} were already saved. Status: Pending Review.")

    with st.expander("Ledger lines that were tested"):
        view = ledger.copy()
        view.insert(0, "line", range(1, len(view) + 1))
        st.dataframe(view, hide_index=True)
