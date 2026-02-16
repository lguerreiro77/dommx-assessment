# core/ui/state_manager.py
import streamlit as st
from typing import Any, Optional


def normalize_bool(value: Any) -> bool:
    # Regra fixa do baseline
    return str(value).strip().lower() == "true"


def init_session_state():
    """
    Um lugar só para inicializar chaves.
    Evita botões funcionando antes do state estabilizar.
    """
    ss = st.session_state

    ss.setdefault("app_ready", False)
    ss.setdefault("current_page", "welcome")  # welcome | projects | questionnaire | results | admin
    ss.setdefault("selected_project_id", None)

    # Dialog control (nunca nested)
    ss.setdefault("open_dialog", None)        # nome do dialog atual
    ss.setdefault("dialog_stack", [])         # histórico para voltar
    ss.setdefault("dialog_payload", {})       # dados do dialog atual

    # UX
    ss.setdefault("flash", None)              # {"type": "success|warning|error|info", "msg": "..."}
    ss.setdefault("busy", False)              # trava botões enquanto processa

    # Marcação de carregamento inicial
    # Você pode setar app_ready=True depois que carregar dados essenciais no fluxo atual (sem forçar rerun aqui)
    if ss["app_ready"] is False:
        ss["app_ready"] = True


def set_flash(msg: str, type_: str = "info"):
    st.session_state["flash"] = {"type": type_, "msg": msg}


def render_flash():
    flash = st.session_state.get("flash")
    if not flash:
        return
    type_ = flash.get("type", "info")
    msg = flash.get("msg", "")
    if type_ == "success":
        st.success(msg)
    elif type_ == "warning":
        st.warning(msg)
    elif type_ == "error":
        st.error(msg)
    else:
        st.info(msg)
    st.session_state["flash"] = None


def safe_set_page(page: str):
    st.session_state["current_page"] = page


def open_dialog(name: str, payload: Optional[dict] = None):
    """
    Abre dialog SEM nested.
    Salva o anterior na stack para voltar.
    """
    ss = st.session_state
    current = ss.get("open_dialog")
    if current:
        ss["dialog_stack"].append(current)
    ss["open_dialog"] = name
    ss["dialog_payload"] = payload or {}


def close_dialog(go_back: bool = True):
    """
    Fecha dialog. Se go_back e tiver stack, volta ao anterior.
    """
    ss = st.session_state
    ss["dialog_payload"] = {}
    if go_back and ss.get("dialog_stack"):
        ss["open_dialog"] = ss["dialog_stack"].pop()
    else:
        ss["open_dialog"] = None
        ss["dialog_stack"] = []


def clear_dialog_stack():
    ss = st.session_state
    ss["dialog_stack"] = []


def set_busy(flag: bool):
    st.session_state["busy"] = bool(flag)


def is_busy() -> bool:
    return bool(st.session_state.get("busy", False))
