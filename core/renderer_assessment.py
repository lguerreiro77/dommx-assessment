import streamlit as st
import os
import yaml
import json
import re
import time
from datetime import datetime

from core.config import BASE_DIR, resolve_path, APP_TITLE
from core.config import get_filesystem_setup_path, get_general_dir, get_project_root

from storage.result_storage import save_results
from storage.export_service import export_all_to_excel
from core.flow_engine import advance_flow, add_message, get_messages
from core.session_utils import logout
from auth.crypto_service import decrypt_text
from storage.log_storage import save_log_snapshot
from core.i18n_markers import mark_yaml_strings

from data.repository_factory import get_repository
repo = get_repository()


# =====================================================
# YAML marker: strings vindas do YAML (não traduzir)
# =====================================================

class _YAMLText(str):
    def __new__(cls, value):
        obj = super().__new__(cls, value)
        obj._dommx_yaml = True  # marcador
        return obj

def _mark_yaml(obj):
    if isinstance(obj, dict):
        return {k: _mark_yaml(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_mark_yaml(v) for v in obj]
    if isinstance(obj, str) and not getattr(obj, "_dommx_yaml", False):
        return _YAMLText(obj)
    return obj

# =========================================================
# HELPERS
# =========================================================

def _normalize_bool_yesno(value, default_if_unknown=True) -> bool:
    if value is None:
        return default_if_unknown
    s = str(value).strip().lower()
    if s == "yes":
        return True
    if s == "no":
        return False
    return default_if_unknown


def _parse_sort_order(raw: str) -> str:
    s = str(raw or "").strip().lower()
    if s in ("id", "sequential"):
        return "id"
    if s in ("natural", "priority"):
        return "natural"
    return "natural"


def _parse_navigation_mode(raw: str) -> str:
    s = str(raw or "").strip().lower()
    if s in ("free",):
        return "free"
    if s in ("sequential", "seq"):
        return "sequential"
    return "free"


def _validate_maturity_scale(raw_scale):
    errors = []
    fallback = [0, 1, 2, 3, 4, 5]

    if raw_scale is None:
        return fallback, errors

    if not isinstance(raw_scale, list) or not raw_scale:
        errors.append(tr("Invalid maturity_scale: must be a non-empty array. Falling back to default [0..5]."))
        return fallback, errors

    out = []
    for x in raw_scale:
        try:
            out.append(int(x))
        except Exception:
            errors.append(tr(f"Invalid maturity_scale value '{x}': must be integer. Falling back to default [0..5]."))
            return fallback, errors

    out = sorted(list(dict.fromkeys(out)))

    bad = [v for v in out if v < 0 or v > 5]
    if bad:
        errors.append(tr(f"Invalid maturity_scale values out of range 0..5: {bad}. Falling back to default [0..5]."))
        return fallback, errors

    return out, errors


def _id_natural_key(qid: str):
    s = str(qid or "")
    nums = re.findall(r"\d+", s)
    if not nums:
        return (10**9, s.lower())
    return (int(nums[0]), s.lower())


def mark_assessment_finished(user_id, project_id):
    repo.insert(
        "finished_assessments",
        {
            "user_id": str(user_id).strip(),
            "project_id": str(project_id).strip(),
            "is_finished": True,
            "timestamp": datetime.utcnow().isoformat()
        }
    )


def safe_load(path):

    if not path:
        st.error("YAML load error: path is None or empty.")
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return data

    except Exception as e:
        st.error(f"YAML load error: {path} | {e}")
        return None
        
        
def render_final_screen():


    st.title(APP_TITLE)
    st.success("Assessment completed successfully.")

    logout_at = st.session_state.get("logout_at")

    if logout_at:
        remaining = int(logout_at - time.time())

        if remaining > 0:
            st.info(f"You will be logged out automatically in {remaining} seconds...")
            time.sleep(1)
            st.rerun()
        else:
            logout()
            st.rerun()

    st.stop()



# =========================================================
# MAIN ASSESSMENT RENDER
# =========================================================

def render_assessment():       
       
        # -------------------------------------------------
        # FINAL SCREEN (fora do dialog)
        # -------------------------------------------------

        if st.session_state.get("final_screen"):
            
            st.success("Assessment completed successfully.")

            start = st.session_state.get("final_start", time.time())
            duration = 5

            elapsed = time.time() - start
            remaining = int(duration - elapsed)

            if remaining > 0:
                st.info(f"You will be logged out automatically in {remaining} seconds...")
                time.sleep(1)
                st.rerun()
            else:
                logout()
                st.rerun()

            st.stop()   
           
        
        fs_path = get_filesystem_setup_path()
        fs_setup = safe_load(fs_path) or {}
        config = (fs_setup.get("orchestrator_config") or {})    
            
        
        active_project = st.session_state.get("active_project")

        data_root = os.path.join(BASE_DIR, "data")

        if active_project:
            root = os.path.join(data_root, "projects", active_project)
        else:
            root = data_root

        flow_path = os.path.join(root, config.get("main_flow"))
        orch_path = os.path.join(root, config.get("main_orchestration"))
            
        if not flow_path:
            st.error("Flow path is None.")
            st.stop()

        if not orch_path:
            st.error("Orchestration path is None.")
            st.stop()

        flow = safe_load(flow_path) or {}
        orch = safe_load(orch_path) or {}       

        req_list = orch.get("execution_request", []) or []
        total_domains = len(req_list)

        if total_domains == 0:
            add_message("No execution_request found in orchestration file.", "error")
            st.stop()

        domain_flow = flow.get("Domain_flow", []) or []    
        
        nav_mode = _parse_navigation_mode(orch.get("navigation_mode", "free"))
        sort_order = _parse_sort_order(orch.get("sort_order", "natural"))

        maturity_scale, scale_errors = _validate_maturity_scale(orch.get("maturity_scale"))
        for e in scale_errors:
            add_message(e, "error")

        st.session_state.dom_idx = max(0, min(int(st.session_state.dom_idx), total_domains - 1))
        current_req = req_list[st.session_state.dom_idx]

        dom_id = current_req.get("domain")
        dom_meta = next(
            (d for d in domain_flow if str(d.get("domain_id")) == str(dom_id)),
            None
        )
        
        
        if not dom_meta:
            add_message(f"Domain metadata not found in flow.yaml for domain_id={dom_id}.", "error")
            st.stop()
        
        project_root = get_project_root()

        if not project_root:
            add_message("Project root not found.", "error")
            st.stop()

        domains_dir = os.path.join(project_root, "Domains")   
            
        current_locale = st.session_state.get("locale")

        if not current_locale:
            st.stop()

        domains_dir = os.path.join(project_root, "Domains")

        tree_path = os.path.join(
            domains_dir,
            current_locale,
            dom_meta["files"]["decision_tree"]
        )

        catalog_path = os.path.join(
            domains_dir,
            current_locale,
            dom_meta["files"]["action_catalog"]
        )
        
        if not os.path.isfile(tree_path):
            tree_path = os.path.join(
                domains_dir,
                DEFAULT_LOCALE,
                dom_meta["files"]["decision_tree"]
            )

        if not os.path.isfile(catalog_path):
            catalog_path = os.path.join(
                domains_dir,
                DEFAULT_LOCALE,
                dom_meta["files"]["action_catalog"]
            )
                
        tree_data = _mark_yaml(safe_load(tree_path) or {})
        catalog_data = _mark_yaml(safe_load(catalog_path) or {})      

        question_block = tree_data.get("questions", {}) or {}
        question_block = {str(k).lower(): v for k, v in question_block.items()}

        selected_questions = current_req.get("selected_questions", []) or []

        if sort_order == "id":
            selected_questions = sorted(selected_questions, key=lambda q: _id_natural_key(q.get("id")))

        total_q_current_domain = len(selected_questions)
        if total_q_current_domain == 0:
            add_message(f"No selected_questions for domain {dom_id}.", "error")
            st.stop()

        st.session_state.q_idx = max(0, min(int(st.session_state.q_idx), total_q_current_domain - 1))

        q_plan = selected_questions[st.session_state.q_idx]
        q_id = q_plan.get("id")
        q_key = str(q_id).lower()

        if q_key not in question_block:
            add_message(f"Question {q_id} not found.", "error")
            st.stop()

        q_content = question_block[q_key] or {}

        is_mandatory = _normalize_bool_yesno(q_plan.get("mandatory", None), True)

        domain_key = f"domain_{st.session_state.dom_idx}"
        
        if "last_save_ts" not in st.session_state:
            st.session_state.last_save_ts = time.time()
            
        if domain_key not in st.session_state.answers:
            st.session_state.answers[domain_key] = {}

        # ===============================
        # LAYOUT
        # ===============================
        st.markdown("""
        <style>
          .dmx-small { font-family: Arial; font-size: 8px; line-height: 1.25; }
          div[data-testid="stButton"] > button { border-radius: 8px; }
        </style>
        """, unsafe_allow_html=True)
        
        st.markdown("""
            <style>
            /* DownloadButton: o button geralmente NÃO é filho direto, então NÃO use '>' */
            div[data-testid="stDownloadButton"] button {
                width: 100% !important;
                border-radius: 8px !important;

                /* aparência tipo secondary */
                background: transparent !important;
                border: 1px solid rgba(0,0,0,0.15) !important;
                box-shadow: none !important;

                /* alinhamento igual aos outros botões */
                padding: 0.75rem 1rem !important;
                display: flex !important;
                justify-content: center !important;
                align-items: center !important;
                gap: 0.5rem !important;

                color: inherit !important;
                font-weight: 400 !important;
            }

            /* texto interno */
            div[data-testid="stDownloadButton"] button * {
                color: inherit !important;
            }

            /* hover parecido */
            div[data-testid="stDownloadButton"] button:hover:not(:disabled) {
                background: rgba(0,0,0,0.04) !important;
            }

            /* disabled consistente */
            div[data-testid="stDownloadButton"] button:disabled {
                opacity: 0.5 !important;
                background: transparent !important;
            }
            </style>
            """, unsafe_allow_html=True)


        col_left, col_main = st.columns([2, 6], gap="small")
        
        # -------------------------------------------------
        # LAST ANSWERED POSITION (must be before navigation panel)
        # -------------------------------------------------

        last_dom = 0
        last_q = -1

        for d_index, req in enumerate(req_list):

            domain_key_check = f"domain_{d_index}"
            sq = req.get("selected_questions", []) or []

            domain_answers = st.session_state.answers.get(domain_key_check, {})

            for q_index, q in enumerate(sq):
                qid = q.get("id")
                if qid in domain_answers:
                    last_dom = d_index
                    last_q = q_index

        # ===============================
        # LEFT PANEL
        # ===============================
        with col_left:

            # ===========================
            # NAV: NÃO TRADUZIR
            # ===========================
            st.session_state["_yaml_rendering"] = True

            nav_box = st.container(border=True)
            with nav_box:
                st.markdown(st._tr("**Navigation**",force=True))

                with st.container(height=320):
                    for i, r in enumerate(req_list):
                        dom_id_i = r.get("domain")
                        meta = next((d for d in domain_flow if str(d.get("domain_id")) == str(dom_id_i)), {}) or {}
                        acr = (meta.get("acronym") or f"D{dom_id_i}").strip()

                        expanded = (i == st.session_state.dom_idx)

                        with st.expander(acr, expanded=expanded):

                            sq = r.get("selected_questions", []) or []
                            if sort_order == "id":
                                sq = sorted(sq, key=lambda q: _id_natural_key(q.get("id")))

                            qids = [q.get("id") for q in sq if q.get("id")]

                            for qi, qx in enumerate(qids):
                                prefix = "▸ " if (i == st.session_state.dom_idx and qi == st.session_state.q_idx) else "  "
                                if st.button(f"{prefix}{qx}", key=f"tree_q_{i}_{qi}", use_container_width=True):

                                    if i > last_dom or (i == last_dom and qi > last_q + 1):
                                        add_message("You cannot navigate to unanswered future questions.","warning")
                                    else:
                                        st.session_state.dom_idx = i
                                        st.session_state.q_idx = qi
                                        st.rerun()

            st.session_state["_yaml_rendering"] = False

            # ===========================
            # MESSAGES: PODE TRADUZIR
            # (add_message já traduz texto)
            # ===========================
            msg_box = st.container(border=True)
            
            st.session_state["_yaml_rendering"] = False
            
            with msg_box:
                st.markdown("**Messages**")
                msgs = get_messages()

                with st.container(height=260):
                    if not msgs:
                        st.markdown(
                                st._html_tr("<div class='dmx-small'>No messages.</div>"),
                                unsafe_allow_html=True
                            )
                    else:
                        for m in msgs:
                            lvl = (m.get("level") or "error").lower()
                            txt = (m.get("text") or "").strip()
                            if not txt:
                                continue

                            color = "#444"
                            tag = "INFO"
                            if lvl == "error":
                                color = "#b71c1c"
                                tag = "ERROR"
                            elif lvl == "warning":
                                color = "#e65100"
                                tag = "WARNING"
                            elif lvl == "success":
                                color = "#1b5e20"
                                tag = "SUCCESS"

                            st.markdown(
                                f"<div class='dmx-small' style='color:{color}; margin-bottom:6px; white-space:pre-wrap;'>[{tag}] {txt}</div>",
                                unsafe_allow_html=True
                            )

        # ===============================
        # MAIN PANEL
        # ===============================
        with col_main:

            col_title, col_menu = st.columns([12, 1])

            with col_title:
                title_acr = (dom_meta.get("acronym") or "").strip()
                title_name = (dom_meta.get("name") or "Domain").strip()
                if title_acr:
                    st.header(f"{title_acr} · {title_name}")
                else:
                    st.header(title_name)

            with col_menu:
                with st.popover("⋮"):

                    st.markdown("### Menu")
                    
                    if st.button("🚪 Log off", use_container_width=True):
                        logout()

                    if st.button("👤 User / Account", use_container_width=True):
                        st.session_state.page = "account"
                        st.rerun()
                    
                    if st.session_state.get("is_admin"):

                        if st.button("🗂 Manage Projects", use_container_width=True):
                            st.session_state.open_dialog = "projects"
                            st.rerun()

                        #can_export = bool(st.session_state.get("last_saved_snapshot"))
                        #excel_data = export_all_to_excel() if can_export else b""
                        
                        # Botão sempre visível
                        if st.button(
                            "📊 Export All Results",
                            key="btn_export_results",
                            use_container_width=True,
                            type="secondary"
                        ):

                            try:
                                excel_data = export_all_to_excel()

                                if not excel_data:
                                    st.warning("No results available for export.")
                                else:
                                    st.download_button(
                                        label="⬇ Download Excel",
                                        data=excel_data,
                                        file_name="DOMMx_Results.xlsx",
                                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                        use_container_width=True,
                                        key="btn_download_results"
                                    )

                            except Exception as e:
                                st.write("EXPORT ERROR:", e)
                                
            st.session_state["_yaml_rendering"] = True
                                
            # ===============================
            # QUESTION TEXT
            # ===============================
            q_text = (q_content.get("question") or q_content.get("text") or "").strip()
            q_desc = (q_content.get("description") or q_content.get("explanation") or "").strip()
            q_obj = (q_content.get("objective") or "").strip()

            mandatory_marker = " *" if is_mandatory else ""

            if q_text:
                st.subheader(f"{q_id}. {q_text}{mandatory_marker}")
            else:
                st.subheader(f"{q_id}{mandatory_marker}")

            if q_desc:
                st.markdown(q_desc)

            if q_obj:
                st.caption(st._tr(f"Objective: {q_obj}", force=True))

            # -------------------------------------------------
            # LIKERT SCALE (DYNAMIC maturity_scale)
            # -------------------------------------------------
            LIKERT = {
                0: ("🔴", st._tr("Initial", force=True), "#d32f2f"),
                1: ("🟠", st._tr("Ad-hoc", force=True), "#f57c00"),
                2: ("🟡", st._tr("Emerging", force=True), "#fbc02d"),
                3: ("🟢", st._tr("Defined", force=True), "#7cb342"),
                4: ("🟢", st._tr("Managed", force=True), "#388e3c"),
                5: ("🔵", st._tr("Optimized", force=True), "#1976d2"),
            }

            st.markdown(st._tr("### Maturity Level", force=True))

            current_answer = (
                st.session_state.answers
                .get(domain_key, {})
                .get(q_id)
            )

            st.markdown("""
                <style>

                /* Likert buttons */
                div[data-testid="stButton"] > button {
                    height: 65px !important;
                    width: 100% !important;
                    padding: 6px !important;
                    display: flex !important;
                    flex-direction: column !important;
                    justify-content: center !important;
                    align-items: center !important;
                    text-align: center !important;
                    white-space: pre-line !important;  /* ESSENCIAL */
                }

                /* Texto interno */
                div[data-testid="stButton"] > button p {
                    margin: 0 !important;
                    line-height: 1.1 !important;
                    font-size: 11px !important;
                }

                </style>
                """, unsafe_allow_html=True)


            cols = st.columns(len(maturity_scale), gap="small")

            for idx, score_value in enumerate(maturity_scale):
                emoji, label, color = LIKERT.get(score_value, ("❓", f"Level {score_value}", "#666"))
                selected = (current_answer == score_value)

                with cols[idx]:

                    if selected:
                        st.markdown(f"""
                        <style>
                        button[key="likert_{q_id}_{score_value}"] {{
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
                        key=f"likert_{q_id}_{score_value}",
                        use_container_width=True,
                        type="secondary",
                    ):
                        if domain_key not in st.session_state.answers:
                            st.session_state.answers[domain_key] = {}
                        st.session_state.answers[domain_key][q_id] = score_value
                        st.rerun()
                   
            # -------------------------------------------------
            # ACTION BLOCK
            # -------------------------------------------------
            
            current_answer = (
                st.session_state.answers
                .get(domain_key, {})
                .get(q_id)
            )

            if current_answer is not None:        
                
                    score = current_answer

                    mapping = q_content.get("score_action_mapping") or {}
                    
                    if score not in mapping:
                        add_message(f"Missing score_action_mapping for score {score} in question {q_id}.", "error")
                    else:
                        action_code = mapping[score].get("action_code")
                        action = (catalog_data.get("action_catalog", {}) or {}).get(action_code)

                        header_color = LIKERT.get(score, ("", "", "#666"))[2]

                        st.divider()
                        
                        if action:
                            action_title = action.get("title", "")
                            action_code_clean = action_code.replace("-", "")

                            st.markdown(f"""
                                <div style="
                                    background-color: {header_color};
                                    padding: 8px 12px;
                                    border-radius: 6px;
                                    color: white;
                                    font-weight: 600;
                                    margin-bottom: 8px;
                                ">
                                    {action_code_clean} - {action_title}
                                </div>
                            """, unsafe_allow_html=True)


                            for proc in action.get("procedures", []):
                                with st.expander(f"Proc {proc['number']}: {proc['name']}"):
                                    if proc.get("prerequisite"):
                                        st.markdown(st._tr("**Prerequisite**",force=True))
                                        st.write(proc["prerequisite"])

                                    if proc.get("deliverable"):
                                        st.markdown(st._tr("**Deliverable**",force=True))
                                        st.write(proc["deliverable"])

                                    if proc.get("recommendations"):
                                        st.markdown(st._tr("**Recommendations**",force=True))
                                        for rec in proc["recommendations"]:
                                            st.write(f"- {rec}")

                                    note_value = proc.get("note") or proc.get("notes")
                                    if note_value:
                                        st.markdown(st._tr("**Note**",force=True))
                                        if isinstance(note_value, list):
                                            for n in note_value:
                                                st.write(f"- {n}")
                                        else:
                                            st.write(note_value)

            
            st.session_state["_yaml_rendering"] = False
            
            # pula espaço entre botoes salvar, proximo, etc.
            st.markdown("<div style='margin-top:35px;'></div>", unsafe_allow_html=True)              
            
            # -------------------------------------------------
            # NO SAVES WARNING  → MESSAGE PANEL - 3 minutes
            # -------------------------------------------------

            if "last_saved_snapshot" in st.session_state:

                changed = st.session_state.answers != st.session_state.last_saved_snapshot

                if changed:
                    elapsed = int(time.time() - st.session_state.last_save_ts)

                    if elapsed > 180:

                        warning_text = f"Last saved {elapsed} seconds ago. You have unsaved changes."

                        existing_msgs = get_messages()

                        already_exists = any(
                            (m.get("text") or "").startswith("Last saved")
                            for m in existing_msgs
                        )

                        if not already_exists:
                            add_message(warning_text, "warning")
                   
            
            # -------------------------------------------------
            # SAVE + NAVIGATION
            # -------------------------------------------------
            total_q = len(selected_questions)

            col_save, col_prev, col_next = st.columns([6, 2, 2])

            # SAVE
            with col_save:

                if "last_saved_snapshot" not in st.session_state:
                    st.session_state.last_saved_snapshot = json.loads(json.dumps(st.session_state.answers))

                changed = st.session_state.answers != st.session_state.last_saved_snapshot

                if st.button(
                    "💾 Save Progress",
                    use_container_width=True,
                    disabled=not changed
                ):

                    save_results(
                        st.session_state.user_id,
                        st.session_state.active_project,
                        st.session_state.answers
                    )

                    st.session_state.last_saved_snapshot = json.loads(json.dumps(st.session_state.answers))
                    st.session_state.last_save_ts = time.time()

                    # Remove warnings antigos
                    msgs = get_messages()
                    filtered = [m for m in msgs if not (m.get("text") or "").startswith("Last saved")]
                    st.session_state.messages = filtered

                    # Adiciona mensagem de sucesso no painel esquerdo
                    add_message("Progress saved successfully.", "success")
                    
                    # Logs
                    save_log_snapshot(
                        st.session_state.user_id,
                        st.session_state.active_project,
                        get_messages()
                    )

                    st.rerun()


            # PREVIOUS
            with col_prev:

                prev_disabled = (
                    st.session_state.dom_idx == 0 and
                    st.session_state.q_idx == 0
                )

                if st.button(
                    "⬅ Previous",
                    use_container_width=True,
                    disabled=prev_disabled
                ):

                    if st.session_state.q_idx > 0:
                        st.session_state.q_idx -= 1
                        st.rerun()

                    else:
                        prev_dom = st.session_state.dom_idx - 1
                        prev_req = req_list[prev_dom]
                        prev_qs = prev_req.get("selected_questions", []) or []
                        if sort_order == "id":
                            prev_qs = sorted(prev_qs, key=lambda q: _id_natural_key(q.get("id")))

                        st.session_state.dom_idx = prev_dom
                        st.session_state.q_idx = max(len(prev_qs) - 1, 0)
                        st.rerun()

            # NEXT
            with col_next:

                answered = (current_answer is not None)
                next_disabled = (not answered) if is_mandatory else False

                at_last_q = (st.session_state.q_idx >= (total_q_current_domain - 1))
                at_last_domain = (st.session_state.dom_idx >= (total_domains - 1))
                is_last_step = at_last_q and at_last_domain

                if not is_last_step:

                    if st.button(
                        "➡ Next",
                        use_container_width=True,
                        disabled=next_disabled
                    ):

                        if is_mandatory and current_answer is None:
                            add_message(
                                f"Mandatory question not answered: {dom_meta.get('acronym','')} / {q_id}.",
                                "error"
                            )
                            st.rerun()

                        advance_flow(total_q_current_domain, total_domains)

                else:

                    # Next desabilitado
                    st.button(
                        "➡ Next",
                        use_container_width=True,
                        disabled=True
                    )

                    # Verificar mandatory pendente
                    mandatory_missing = False

                    for dom_index, req in enumerate(req_list):

                        domain_key_check = f"domain_{dom_index}"
                        sq = req.get("selected_questions", []) or []

                        domain_answers = st.session_state.answers.get(domain_key_check, {})

                        for q in sq:

                            is_mandatory_q = str(q.get("mandatory", False)).strip().lower() in ["true", "yes", "1"]

                            if is_mandatory_q:
                                qid = q.get("id")
                                if qid not in domain_answers:
                                    mandatory_missing = True
                                    break

                        if mandatory_missing:
                            break


                    # Botão Submit
                    if st.button(
                        "✅ Submit All",
                        use_container_width=True,
                        type="primary",
                        disabled=mandatory_missing
                    ):
                        if mandatory_missing:
                            add_message(
                                "There are mandatory questions not answered. Please complete them before submitting.",
                                "error"
                            )
                        else:
                            st.session_state.open_submit_dialog = True

            # =========================
            # MODAL FORA DAS COLUNAS
            # =========================
            if st.session_state.get("open_submit_dialog"):

                if st.session_state.get("open_submit_dialog"):

                    st.warning(
                        "This action is final. You will not be able to modify the results after submission."
                    )

                    st.markdown("Do you want to proceed?")

                    col1, col2 = st.columns(2)

                    with col1:
                        if st.button("Confirm", use_container_width=True):
                            
                            mark_assessment_finished(
                                st.session_state.user_id,
                                st.session_state.active_project
                            )                        
                            
                            save_log_snapshot(
                                st.session_state.user_id,
                                st.session_state.active_project,
                                get_messages()
                            )
                            
                            st.session_state.final_screen = True
                            st.session_state.final_start = time.time()

                            st.session_state.open_submit_dialog = False
                            st.rerun()                      
                            
                    with col2:
                        if st.button("Cancel", use_container_width=True):
                            st.session_state.open_submit_dialog = False
                            st.rerun()

        st.session_state["_yaml_rendering"] = False
    
    