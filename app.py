import streamlit as st
from core.state import init_session
from auth.auth_service import render_auth
from core.renderer import render_app
from core.config import APP_TITLE

st.set_page_config(page_title=APP_TITLE, layout="centered")

init_session()

# Se estiver em modo autenticação, NÃO mostrar título grande
if st.session_state.app_mode in ["login", "register", "select_project"]:
    render_auth()
else:
    # Só mostra título grande após login
    st.title(APP_TITLE)
    render_app()
