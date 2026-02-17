import streamlit as st
import json
from storage.result_storage import load_results
from core.flow_engine import ensure_started_message


def initialize_renderer(req_list):

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

            # 🔥 Reconstruir posição automaticamente
            found_position = False

            for d_index, req in enumerate(req_list):

                dom_id = req.get("domain")
                sq = req.get("selected_questions", []) or []

                domain_answers = st.session_state.answers.get(dom_id, {})

                for q_index, q in enumerate(sq):
                    qid = q.get("id")

                    if qid not in domain_answers:
                        st.session_state.dom_idx = d_index
                        st.session_state.q_idx = q_index
                        found_position = True
                        break

                if found_position:
                    break

            # Se todas respondidas → posiciona no último
            if not found_position and req_list:
                st.session_state.dom_idx = len(req_list) - 1
                last_sq = req_list[-1].get("selected_questions", []) or []
                st.session_state.q_idx = max(len(last_sq) - 1, 0)

            # snapshot inicial
            st.session_state.last_saved_snapshot = json.loads(
                json.dumps(st.session_state.answers)
            )

        st.session_state.loaded_from_storage = True

