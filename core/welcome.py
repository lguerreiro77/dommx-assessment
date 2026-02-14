import streamlit as st
from core.config import BASE_DIR, resolve_path
import yaml

def safe_load(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except:
        return None

def render_welcome():

    config_path = resolve_path(BASE_DIR, "data/general/app_config.yaml")
    config = safe_load(config_path)

    intro_heading = config.get("intro", {}).get("heading", "")
    intro_message = config.get("intro", {}).get("message", "")
    show_intro = config.get("app", {}).get("show_intro", False)

    if not show_intro:
        st.session_state.intro_seen = True
        st.rerun()

    st.markdown(f"<h2 style='text-align:center'>{intro_heading}</h2>", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    st.markdown(
        f"<div style='text-align:center; max-width:700px; margin:auto;'>"
        f"{intro_message}"
        f"</div>",
        unsafe_allow_html=True
    )

    st.markdown("<br><br>", unsafe_allow_html=True)

    col1, col2 = st.columns([8,2])

    with col2:
        if st.button("Continue ➡", use_container_width=True):
            st.session_state.intro_seen = True
            st.rerun()
