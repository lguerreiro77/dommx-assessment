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

    from pathlib import Path
    import yaml

    # mesma lógica usada no app.py sem importar o módulo
    project_id = st.session_state.get("active_project")

    config = {}

    if project_id:
        project_config = Path("data/projects") / str(project_id) / "General" / "app_config.yaml"
        if project_config.exists():
            with open(project_config, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}

    if not config:
        global_config = Path("data/general/app_config.yaml")
        if global_config.exists():
            with open(global_config, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}

    intro_heading = config.get("intro", {}).get("heading", "")
    intro_message = config.get("intro", {}).get("message", "")
    show_intro = config.get("app", {}).get("show_intro", False)

    if not show_intro:
        st.session_state.intro_seen = True
        st.rerun()

    st.markdown(
        st._html_tr(f"<h2 style='text-align:center'>{intro_heading}</h2>"),
        unsafe_allow_html=True
    )

    st.markdown("<br>", unsafe_allow_html=True)

    st.markdown(
        st._html_tr(
            f"<div style='text-align:center; max-width:700px; margin:auto;'>"
            f"{intro_message}"
            f"</div>"
        ),
        unsafe_allow_html=True
    )

    st.markdown("<br><br>", unsafe_allow_html=True)

    col1, col2 = st.columns([8, 2])

    with col2:
        if st.button("Continue ➡", use_container_width=True):
            st.session_state.intro_seen = True
            st.rerun()
