import time
import streamlit as st


# =========================================================
# ASSESSMENT MESSAGES
# - Apenas mensagens relevantes (error/warning/success)
# =========================================================
_ALLOWED_LEVELS = {"error", "warning", "success"}


def add_message(text: str, level: str = "error"):
    level = (level or "error").strip().lower()
    if level not in _ALLOWED_LEVELS:
        return

    if "assessment_messages" not in st.session_state:
        st.session_state.assessment_messages = []

    if isinstance(text, str):
        try:
            text = st._tr(text, force=True)
        except Exception:
            pass

    st.session_state.assessment_messages.append({
        "ts": time.time(),
        "level": level,
        "text": str(text or "").strip()
    })


def get_messages():
    msgs = st.session_state.get("assessment_messages", [])
    msgs = [m for m in msgs if (m.get("text") or "").strip()]
    return sorted(msgs, key=lambda x: x.get("ts", 0), reverse=True)


def clear_messages():
    st.session_state.assessment_messages = []


def ensure_started_message():
    # NÃO poluir painel com "started" (user pediu sem navegação/info)
    if st.session_state.get("_assessment_started_msg"):
        return
    st.session_state._assessment_started_msg = True


# =========================================================
# FLOW ADVANCE
# - Não gera mensagens de navegação
# =========================================================
def advance_flow(total_questions_in_domain: int, total_domains: int):
    """
    Avança questionário.
    - Se ainda há questões no domínio: q_idx += 1
    - Se acabou o domínio: dom_idx += 1 e q_idx = 0
    - Se acabou tudo: marca assessment_completed
    """

    ensure_started_message()

    q_idx = int(st.session_state.get("q_idx", 0))
    dom_idx = int(st.session_state.get("dom_idx", 0))

    if q_idx < (total_questions_in_domain - 1):
        st.session_state.q_idx = q_idx + 1
        st.rerun()

    next_dom = dom_idx + 1

    if next_dom < total_domains:
        st.session_state.dom_idx = next_dom
        st.session_state.q_idx = 0
        st.rerun()

    st.session_state.assessment_completed = True
    add_message("Assessment completed successfully.", "success")
    st.rerun()
