import streamlit as st

from core.renderer_init import initialize_renderer
from core.renderer_controller import handle_page_and_dialogs
from core.renderer_assessment import render_assessment


def render_app():
    try:
        initialize_renderer()

        # controla account + modais
        if handle_page_and_dialogs():
            return

        # roda assessment principal
        render_assessment()

    except Exception as e:
        from core.flow_engine import add_message
        add_message(f"Renderer error: {e}", "error")
        st.exception(e)
