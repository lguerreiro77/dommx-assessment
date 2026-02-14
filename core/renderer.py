import streamlit as st
from core.config import BASE_DIR, resolve_path
from storage.result_storage import save_results
from storage.export_service import export_all_to_excel
from core.welcome import render_welcome
import yaml
import os
import json


def safe_load(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except:
        return None


def render_app():

    try:
        
        if not st.session_state.get("intro_seen", False):
           render_welcome()

        # -------------------------------------------------
        # LOAD CORE FILES
        # -------------------------------------------------

        fs_path = resolve_path(BASE_DIR, "FileSystem_Setup.yaml")
        fs_setup = safe_load(fs_path)
        config = fs_setup["orchestrator_config"]

        flow_path = resolve_path(BASE_DIR, config["main_flow"])
        orch_path = resolve_path(BASE_DIR, config["main_orchestration"])

        flow = safe_load(flow_path)
        orch = safe_load(orch_path)

        req_list = orch["execution_request"]
        current_req = req_list[st.session_state.dom_idx]

        domain_flow = flow["Domain_flow"]

        dom_meta = next(
            (d for d in domain_flow
             if str(d["domain_id"]) == str(current_req["domain"])),
            None
        )

        lang = orch.get("language", "Default")

        tree_path = resolve_path(
            BASE_DIR,
            f"data/domains/Language/{lang}/{dom_meta['files']['decision_tree']}"
        )

        catalog_path = resolve_path(
            BASE_DIR,
            f"data/domains/Language/{lang}/{dom_meta['files']['action_catalog']}"
        )

        tree_data = safe_load(tree_path)
        catalog_data = safe_load(catalog_path)

        question_block = tree_data["questions"]
        question_block = {k.lower(): v for k, v in question_block.items()}

        selected_questions = current_req["selected_questions"]

        q_plan = selected_questions[st.session_state.q_idx]
        q_id = q_plan["id"]
        q_key = q_id.lower()

        if q_key not in question_block:
            st.error(f"Question {q_id} not found.")
            st.stop()

        q_content = question_block[q_key]

        # -------------------------------------------------
        # QUESTION HEADER
        # -------------------------------------------------

        col_title, col_menu = st.columns([12, 1])

        with col_title:
            st.header(dom_meta["name"])

        with col_menu:
            if st.session_state.get("is_admin"):
                with st.popover("⋮"):
                    st.markdown("### Admin")
                    if st.button("📊 Export All Results", use_container_width=True):
                        file_path = export_all_to_excel()
                        st.success("Export completed.")

        st.markdown("<br>", unsafe_allow_html=True)

        st.subheader(f"{q_id}: {q_content.get('text','')}")

        if q_content.get("explanation"):
            st.markdown(
                f"<div style='font-size:14px;color:gray;font-style:italic;'>"
                f"{q_content['explanation']}"
                f"</div>",
                unsafe_allow_html=True
            )

        st.markdown("<br>", unsafe_allow_html=True)


        # -------------------------------------------------
        # LIKERT SCALE (ORIGINAL)
        # -------------------------------------------------

        LIKERT = {
            0: ("🔴", "Initial", "#d32f2f"),
            1: ("🟠", "Ad-hoc", "#f57c00"),
            2: ("🟡", "Developing", "#fbc02d"),
            3: ("🟢", "Defined", "#7cb342"),
            4: ("🟢", "Managed", "#388e3c"),
            5: ("🔵", "Optimized", "#1976d2"),
        }

        st.markdown("### Maturity Level")

        current_answer = st.session_state.answers.get(q_id)

        cols = st.columns(6)

        for i, col in enumerate(cols):
            emoji, label, color = LIKERT[i]
            selected = (current_answer == i)

            with col:

                if selected:
                    st.markdown(
                        f"""
                        <style>
                        div[data-testid="stButton"] > button[kind="secondary"][key="{q_id}_{i}"] {{
                            background: {color} !important;
                            color: white !important;
                            border: 1px solid {color} !important;
                        }}
                        </style>
                        """,
                        unsafe_allow_html=True,
                    )

                clicked = st.button(
                    f"{emoji}\n{label}",
                    key=f"{q_id}_{i}",
                    use_container_width=True,
                    type="secondary",
                )

                if clicked:
                    st.session_state.answers[q_id] = i
                    st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)

        # -------------------------------------------------
        # ACTION BLOCK (EXATAMENTE COMO ORIGINAL)
        # -------------------------------------------------

        if q_id in st.session_state.answers:
            score = st.session_state.answers[q_id]

            mapping = q_content.get("score_action_mapping")
            action_code = mapping[score]["action_code"]
            action = catalog_data.get("action_catalog", {}).get(action_code)

            header_color = LIKERT[score][2]

            st.divider()

            st.markdown(
                f"""
                <div style="
                    background:{header_color};
                    padding:18px;
                    border-radius:10px;
                    margin-top:10px;
                    color:white;
                    font-weight:700;
                    font-size:20px;">
                    Prescriptive Action: {action_code}
                </div>
                """,
                unsafe_allow_html=True,
            )

            if action:
                st.markdown(f"**{action.get('title','')}**")

                for proc in action.get("procedures", []):
                    if proc.get("number") in q_plan.get("procedures", []):
                        with st.expander(f"Proc {proc['number']}: {proc['name']}"):

                            if proc.get("prerequisite"):
                                st.markdown("**Prerequisite**")
                                st.write(proc["prerequisite"])

                            if proc.get("deliverable"):
                                st.markdown("**Deliverable**")
                                st.write(proc["deliverable"])

                            if proc.get("recommendations"):
                                st.markdown("**Recommendations**")
                                for rec in proc["recommendations"]:
                                    st.write(f"- {rec}")

                            note_value = proc.get("note") or proc.get("notes")
                            if note_value:
                                st.markdown("**Note**")
                                if isinstance(note_value, list):
                                    for n in note_value:
                                        st.write(f"- {n}")
                                else:
                                    st.write(note_value)

        # -------------------------------------------------
        # SAVE + NAVIGATION (ORIGINAL)
        # -------------------------------------------------

        total_q = len(selected_questions)
        nav_mode = (orch.get("navigation_mode", "Sequential") or "Sequential").lower()

        col_save, col_prev, col_next = st.columns([6, 2, 2])

        # SAVE
        with col_save:

            has_answers = len(st.session_state.answers) > 0
            changed = st.session_state.answers != st.session_state.last_saved_snapshot

            if has_answers:
                if st.button(
                    "💾 Save Progress",
                    use_container_width=True,
                    disabled=not changed
                ):

                    save_results(
                        st.session_state.user_id,
                        {
                            "answers": st.session_state.answers,
                            "last_session": {
                                "dom_idx": st.session_state.dom_idx,
                                "q_idx": st.session_state.q_idx
                            }
                        }
                    )

                    st.session_state.last_saved_snapshot = dict(st.session_state.answers)
                    st.session_state.just_saved = True
                    st.rerun()

        if st.session_state.get("just_saved"):
            st.success("Progress saved.")
            st.session_state.just_saved = False

        # PREVIOUS
        with col_prev:
            if nav_mode == "free":
                prev_disabled = st.session_state.q_idx == 0
                if st.button(
                    "⬅ Previous",
                    use_container_width=True,
                    disabled=prev_disabled
                ):
                    st.session_state.q_idx -= 1
                    st.rerun()

        # NEXT
        with col_next:
            next_disabled = (
                current_answer is None or
                st.session_state.q_idx >= total_q - 1
            )

            if st.button(
                "➡ Next",
                use_container_width=True,
                disabled=next_disabled
            ):
                st.session_state.q_idx += 1
                st.rerun()

    except Exception as e:
        st.error(f"Erro no renderer: {e}")
        st.exception(e)
