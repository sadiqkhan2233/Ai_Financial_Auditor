import streamlit as st


def flash(message: str, kind: str = "success"):
    """Remembers a message to show after the page reloads."""
    st.session_state["flash_message"] = (kind, message)


def show_flash():
    item = st.session_state.pop("flash_message", None)
    if item:
        getattr(st, item[0])(item[1])
