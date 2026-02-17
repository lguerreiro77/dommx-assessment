import streamlit as st
import json
from storage.result_storage import load_results
from core.flow_engine import ensure_started_message


def initialize_renderer():

    if not st.session_state.get("user_id"):
        st.stop()

    if "assessment_messages" not in st.session_state:
        st.session_state.assessment_messages = []

    ensure_started_message()

    if st.session_state.get("assessment_completed"):
        st.success("Assessment completed successfully.")
        st.stop()

    if "answers" not in st.session_state:
        st.session_state.answers = {}

    if "dom_idx" not in st.session_state:
        st.session_state.dom_idx = 0

    if "q_idx" not in st.session_state:
        st.session_state.q_idx = 0

    if "loaded_from_storage" not in st.session_state:
        st.session_state.loaded_from_storage = False

    if "intro_seen" not in st.session_state:
        st.session_state.intro_seen = False

    if "last_saved_snapshot" not in st.session_state:
        st.session_state.last_saved_snapshot = {}

    # ==========================================
    # Carregar storage uma única vez
    # ==========================================
    if not st.session_state.loaded_from_storage:

        saved = load_results(
            st.session_state.user_id,
            st.session_state.active_project
        )

        if saved:
            st.session_state.answers = saved.get("answers", {}) or {}

            st.session_state.last_saved_snapshot = json.loads(
                json.dumps(st.session_state.answers)
            )

        st.session_state.loaded_from_storage = True