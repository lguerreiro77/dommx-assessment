import streamlit as st
import yaml
import os
import json

from core.config import BASE_DIR, resolve_path
from storage.result_storage import save_results
from storage.export_service import export_all_to_excel
from core.welcome import render_welcome
from storage.result_storage import load_results
from core.projects import render_projects_modal
from core.user_project_modal import render_user_project_modal, render_remove_association_modal




def logout():
    for key in list(st.session_state.keys()):
        del st.session_state[key]

    st.session_state.app_mode = "login"
    st.rerun()


def safe_load(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except:
        return None


def render_app():

    try:
        
        if not st.session_state.get("user_id"):
            st.stop()
        
        # -------------------------
        # MODAL CONTROLLER
        # -------------------------
        
        dialog = st.session_state.pop("open_dialog", None)

        if dialog == "projects":
            render_projects_modal()
        elif dialog == "associate":
            render_user_project_modal()
        elif dialog == "remove_association":
            render_remove_association_modal()


        # -------------------------
        # LOAD SAVED SESSION (APENAS UMA VEZ)
        # -------------------------
        if not st.session_state.get("loaded_from_storage", False):
            saved = load_results(st.session_state.user_id)
            if saved:
                st.session_state.answers = saved.get("answers", {})
                st.session_state.dom_idx = saved.get("dom_idx", 0)
                st.session_state.q_idx = saved.get("q_idx", 0)
                st.session_state.last_saved_snapshot = dict(st.session_state.answers)

            st.session_state.loaded_from_storage = True


        # -------------------------
        # INTRO SCREEN
        # -------------------------
        if not st.session_state.get("intro_seen", False):
            render_welcome()
            return

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

        from storage.google_sheets import get_sheet

        with col_menu:

            with st.popover("⋮"):

                st.markdown("### Menu")

                # ---------------------
                # LOG OFF (todos)
                # ---------------------
                if st.button("🚪 Log off", key="menu_logoff", use_container_width=True):
                    for key in list(st.session_state.keys()):
                        del st.session_state[key]

                    st.session_state.app_mode = "login"
                    st.rerun()

                # ---------------------
                # ADMIN
                # ---------------------
                if st.session_state.get("is_admin"):

                    st.markdown("---")
                    st.markdown("### Admin")

                    col1, col2 = st.columns(2)

                    with col1:
                        if st.button("🗂 Manage Projects", use_container_width=True, key="menu_projects"):
                            st.session_state.open_dialog = "projects"
                            st.rerun()

                    with col2:
                        can_export = bool(st.session_state.get("last_saved_snapshot"))

                        if can_export:
                            excel_data = export_all_to_excel()
                        else:
                            excel_data = b""

                        st.download_button(
                            label="📊 Export All Results",
                            data=excel_data,
                            file_name="DOMMx_Results.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True,
                            disabled=not can_export,
                            key="menu_export"
                        )


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

        # CSS fixo para todos os botões
        st.markdown("""
        <style>
        div[data-testid="stButton"] > button {
            height: 60px !important;
            width: 100% !important;
            padding: 8px 6px !important;

            display: flex !important;
            flex-direction: column !important;
            justify-content: center !important;
            align-items: center !important;

            line-height: 1.1 !important;
            white-space: normal !important;
        }
        </style>
        """, unsafe_allow_html=True)

        cols = st.columns(6, gap="small")

        for i, col in enumerate(cols):
            emoji, label, color = LIKERT[i]
            selected = (current_answer == i)

            with col:

                # Estilo do selecionado (SEM usar primary)
                if selected:
                    st.markdown(f"""
                    <style>
                    button[key="likert_{q_id}_{i}"] {{
                        background: {color} !important;
                        color: white !important;
                        border: 1px solid {color} !important;
                        transform: translateY(2px) !important;
                        box-shadow: inset 0 2px 6px rgba(0,0,0,0.25) !important;
                    }}
                    </style>
                    """, unsafe_allow_html=True)

                if st.button(
                    f"{emoji}\n{label}",
                    key=f"likert_{q_id}_{i}",
                    use_container_width=True,
                    type="secondary",   # SEMPRE secondary
                ):
                    st.session_state.answers[q_id] = i
                    st.rerun()



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
