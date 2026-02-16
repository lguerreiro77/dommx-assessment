# core/ui/layout.py
import streamlit as st
from core.ui.state_manager import render_flash
from core.ui.components import badge


def render_layout():
    """
    Layout base: título, sidebar simples, mensagens.
    Não faz leitura de dados nem chama storage.
    """
    st.set_page_config(page_title="DOMMx Technical Diagnostic Stack", layout="wide")

    with st.sidebar:
        st.markdown("## DOMMx")
        badge("Technical Diagnostic Stack")
        st.divider()
        st.caption("Google Sheets como único datastore. Evitar leituras excessivas.")
        st.divider()

        page = st.session_state.get("current_page", "welcome")
        st.caption(f"Página: **{page}**")

        proj = st.session_state.get("selected_project_id")
        if proj:
            st.caption(f"Projeto: **{proj}**")

    # topo + mensagens
    st.markdown("# DOMMx Assessment")
    render_flash()
