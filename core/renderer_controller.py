import streamlit as st
import time

from core.session_utils import logout
from core.projects import render_projects_modal
from core.user_project_modal import render_user_project_modal, render_remove_association_modal
from core.account import render_account_page
from core.welcome import render_welcome


def handle_page_and_dialogs():
   
    # PAGE CONTROLLER
    page = st.session_state.get("page", "main")

    if page == "account":
        col_a, col_b = st.columns([2, 10])
        with col_a:
            if st.button("⬅ Back", use_container_width=True):
                st.session_state.page = "main"
                st.rerun()

        render_account_page(st.session_state)
        return True

    # MODAL CONTROLLER
    dialog = st.session_state.get("open_dialog")

    if dialog == "projects":
        render_projects_modal()
    elif dialog == "associate":
        render_user_project_modal()
    elif dialog == "remove_association":
        render_remove_association_modal()

    # INTRO SCREEN
    if not st.session_state.get("intro_seen", False):
        render_welcome()
        return True

    return False
