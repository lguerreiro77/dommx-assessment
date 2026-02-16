# core/ui/components.py
import streamlit as st
from typing import Optional
from core.ui.state_manager import is_busy


def disabled_if_not_ready(extra_condition: bool = False) -> bool:
    # trava botões antes de app_ready ou se busy
    ss = st.session_state
    return (not ss.get("app_ready", False)) or is_busy() or extra_condition


def safe_button(label: str, key: Optional[str] = None, disabled: bool = False, help: Optional[str] = None) -> bool:
    return st.button(label, key=key, disabled=disabled_if_not_ready(disabled), help=help)


def section_title(text: str):
    st.markdown(f"### {text}")


def hint(text: str):
    st.caption(text)


def badge(text: str):
    st.markdown(f"`{text}`")


def empty_state(title: str, msg: str):
    st.info(f"**{title}**\n\n{msg}")
