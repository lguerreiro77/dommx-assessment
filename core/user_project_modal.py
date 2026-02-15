import streamlit as st
from storage.user_storage import load_user_by_hash
from storage.user_project_storage import (
    get_all_user_projects,
    save_user_projects,
)
from storage.project_storage import get_projects
from storage.user_storage import get_all_users
from storage.project_storage import get_all_projects
from storage.user_project_storage import associate_users_projects
from storage.google_sheets import get_spreadsheet


if "project_msg" in st.session_state:
    st.success(st.session_state.project_msg)
    del st.session_state["project_msg"]

@st.dialog("Associate Users to Projects", width="Medium")
def render_user_project_modal():
    
    st.session_state["_dialog_open"] = True

    # -------------------------
    # CLOSE BUTTON
    # -------------------------
    if st.button("Close", use_container_width=True):
        st.session_state.active_modal = None
        st.rerun()

    st.divider()

    # -------------------------
    # LOAD DATA (cached)
    # -------------------------
    users = get_all_users()
    projects = get_all_projects()

    if not users:
        st.warning("No users found.")
        st.session_state["_dialog_open"] = False
        return

    if not projects:
        st.warning("No projects found.")
        st.session_state["_dialog_open"] = False
        return

    # -------------------------
    # BUILD DISPLAY OPTIONS
    # -------------------------
    user_options = {        
        u["email_hash"]: f"{u['full_name']} ({u['email']})"
        for u in users
    }

    project_options = {
        p["project_id"]: p["name"]
        for p in projects
        if p.get("is_active", True)
    }

    # -------------------------
    # SELECT USERS
    # -------------------------
    st.markdown("### Select Users")

    selected_users = st.multiselect(
        "Users",
        options=list(user_options.keys()),
        format_func=lambda x: user_options[x]
    )

    # -------------------------
    # SELECT PROJECTS
    # -------------------------
    st.markdown("### Select Projects")

    selected_projects = st.multiselect(
        "Projects",
        options=list(project_options.keys()),
        format_func=lambda x: project_options[x]
    )

    st.divider()

    # -------------------------
    # ASSOCIATE
    # -------------------------
    if st.button("Associate", use_container_width=True):

        if not selected_users:
            st.warning("Select at least one user.")
            return

        if not selected_projects:
            st.warning("Select at least one project.")
            return

        associate_users_projects(
            selected_users,
            selected_projects,
            st.session_state.user_id
        )

        st.session_state._flash = {
            "msg": "Users successfully associated.",
            "level": "success"
        }

        st.rerun()
