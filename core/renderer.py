# core/renderer_v2.py
import streamlit as st

from core.ui.state_manager import init_session_state
from core.ui.layout import render_layout
from core.ui.navigation import render_navigation
from core.ui.dialogs import render_dialog_if_any


def render():
    """
    Renderer V2 (seguro): não altera renderer.py atual.
    Para usar: no seu main.py (ou app.py) troque:
        from core.renderer import render
    por:
        from core.renderer_v2 import render
    """
    init_session_state()
    render_layout()
    render_dialog_if_any()
    render_navigation()
