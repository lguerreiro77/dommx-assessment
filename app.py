import streamlit as st
import time

from core.state import init_session
from auth.auth_service import render_auth
from core.renderer import render_app
from core.config import APP_TITLE
from core.session_utils import logout

st.set_page_config(page_title=APP_TITLE, layout="centered")

init_session()

# -------------------------------------------------
# PROJECT CONFIG ERROR SCREEN (logout in 4s)
# -------------------------------------------------
if st.session_state.get("project_config_error"):
    msg = st.session_state.get("project_config_error_msg") or "Project configuration directory does not exist."
    st.error(msg)

    logout_at = st.session_state.get("logout_at")
    if logout_at:
        remaining = int(float(logout_at) - time.time())
        if remaining > 0:
            st.info(f"You will be logged out automatically in {remaining} seconds...")
            time.sleep(1)
            st.rerun()
        else:
            logout()
    else:
        logout()

    st.stop()

# Auth modes
if st.session_state.app_mode in ["login", "register", "select_project"]:
    render_auth()
else:
    st.title(APP_TITLE)
    render_app()
