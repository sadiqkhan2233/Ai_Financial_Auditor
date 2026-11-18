import streamlit as st

from services.data_access import list_engagements
from services.sample_loader import load_sample_data


def pick_engagement():
    """Returns the chosen engagement id, or None if there is no saved data yet."""
    engagements = list_engagements()
    if not engagements:
        st.info("No saved data yet. Upload a file in the Document Upload Center, or load the built-in sample.")
        if st.button("Load sample data now"):
            try:
                load_sample_data()
                st.rerun()
            except Exception as err:
                st.error(f"Could not load the sample data: {err}")
        return None
    labels = {e["label"]: e["id"] for e in engagements}
    choice = st.selectbox("Engagement", list(labels))
    return labels[choice]
