import streamlit as st
from storage.user_storage import get_all_users, load_user, load_user_by_hash
from storage.project_storage import get_all_projects
from storage.user_project_storage import get_projects_for_user
from storage.result_storage import load_results


def logout():
    try:
        get_all_users.clear()
        load_user.clear()
        load_user_by_hash.clear()
        get_all_projects.clear()
        get_projects_for_user.clear()
        load_results.clear()
    except:
        pass

    st.session_state.clear()
    st.session_state.app_mode = "login"
    st.rerun()
