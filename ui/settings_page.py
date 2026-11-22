from datetime import datetime

import streamlit as st

from config.settings import get_settings
from services.backup_service import create_backup, inspect_backup_bytes, restore_backup, sqlite_path
from ui.flash import flash, show_flash
from ui.identity import get_identity

SESSION_KEYS = ["agent_outputs", "flow_runs", "chat_history", "report_previews", "backup_bytes", "control_saved"]


def _backup_section():
    st.write("Streamlit Community Cloud can erase the database when the app restarts. Download a backup "
             "before you leave, and restore it next time.")
    if st.button("Prepare backup file"):
        try:
            st.session_state["backup_bytes"] = create_backup()
            st.session_state["backup_time"] = datetime.now().strftime("%Y%m%d_%H%M")
        except Exception as err:
            st.error(f"Could not create the backup: {err}")
    if "backup_bytes" in st.session_state:
        st.download_button("⬇ Download backup", st.session_state["backup_bytes"],
                           file_name=f"finaudit_backup_{st.session_state.get('backup_time', 'now')}.db",
                           mime="application/octet-stream")
        st.caption("This file holds ALL client data and is not encrypted. Keep it safe and never upload it to GitHub.")


def _restore_section(username):
    st.markdown("**Restore from a backup**")
    st.warning("Restoring REPLACES everything currently in the app (companies, findings, reports, AI results "
               "and the activity log) with the contents of the file.")
    uploaded = st.file_uploader("Choose a backup file (.db)", type=["db", "sqlite"], key="restore_file")
    if uploaded is None:
        return
    data = uploaded.getvalue()
    try:
        summary = inspect_backup_bytes(data)
    except ValueError as err:
        st.error(str(err))
        return
    st.success("This looks like a valid backup. It contains: " + ", ".join(f"{n} {t}" for t, n in summary.items()) + ".")
    confirm = st.text_input("Type RESTORE to confirm", key="restore_confirm")
    if st.button("Restore this backup", disabled=confirm != "RESTORE"):
        try:
            result = restore_backup(data, username or "Unknown")
        except ValueError as err:
            st.error(str(err))
            return
        st.cache_resource.clear()
        for key in SESSION_KEYS:
            st.session_state.pop(key, None)
        flash("Backup restored: " + ", ".join(f"{n} {t}" for t, n in result.items()) + ".")
        st.rerun()


def show_settings():
    st.title("⚙️ Settings")
    show_flash()
    s = get_settings()
    st.write(f"**AI model:** `{s.groq_model}`")
    st.write(f"**Maximum upload size:** {s.max_upload_mb} MB")
    st.write(f"**API key:** {'Set' if s.groq_api_key else 'Not set'}")
    st.warning(
        "Demo storage notice: this app uses SQLite and temporary file storage. Data can disappear when the cloud "
        "app restarts. This is fine for a portfolio demo but not for real client data. The design allows a later "
        "move to PostgreSQL and private cloud storage."
    )
    st.info("To change the model or key, edit them in Streamlit Cloud → App settings → Secrets.")

    st.subheader("Backup and restore")
    username, role = get_identity()
    if sqlite_path() is None:
        st.info("Backup and restore are only available with the built-in SQLite database.")
    elif role != "Admin":
        st.info("Only an Admin can back up or restore the database. Change your role in the sidebar.")
    else:
        _backup_section()
        st.divider()
        _restore_section(username)
