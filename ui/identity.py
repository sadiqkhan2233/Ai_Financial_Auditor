import streamlit as st

from services.user_service import ROLES, register_user


def show_identity_sidebar():
    st.sidebar.divider()
    st.sidebar.subheader("Who is working?")
    name = st.sidebar.text_input("Your name", value=st.session_state.get("user_name", ""), key="user_name_input")
    current_role = st.session_state.get("user_role", "Auditor")
    role = st.sidebar.selectbox("Your role", ROLES, index=ROLES.index(current_role), key="user_role_input")
    name = name.strip()
    st.session_state["user_name"], st.session_state["user_role"] = name, role
    if name and st.session_state.get("_registered") != (name, role):
        try:
            register_user(name, role)
            st.session_state["_registered"] = (name, role)
        except Exception:
            pass
    st.sidebar.caption("Demo only: there are no passwords. Your name and role are recorded for "
                       "accountability, but this is not real access control.")


def get_identity():
    return st.session_state.get("user_name", ""), st.session_state.get("user_role", "Auditor")
