import streamlit as st
from core.state import init_session
from auth.auth_service import require_login
from core.renderer import render_app
from core.config import APP_TITLE
from core.welcome import render_welcome

st.set_page_config(page_title=APP_TITLE, layout="wide")
st.title(APP_TITLE)

init_session()
require_login()

if not st.session_state.get("intro_seen", False):
    render_welcome()
    st.stop()

render_app()
