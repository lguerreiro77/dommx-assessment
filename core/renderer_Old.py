import streamlit as st
import yaml
import os
import json
import re

from core.config import BASE_DIR, resolve_path
from storage.result_storage import save_results
from storage.export_service import export_all_to_excel
from core.welcome import render_welcome
from storage.result_storage import load_results
from core.projects import render_projects_modal
from core.user_project_modal import render_user_project_modal, render_remove_association_modal
from core.account import render_account_page

from storage.user_storage import get_all_users, load_user, load_user_by_hash
from storage.project_storage import get_all_projects
from storage.user_project_storage import get_projects_for_user

from storage.google_sheets import get_sheet

from core.flow_engine import advance_flow, add_message, get_messages, ensure_started_message


# =========================================================
# HELPERS
# =========================================================
def _normalize_bool_yesno(value, default_if_unknown=True) -> bool:
    """
    mandatory:
      - "Yes" => True
      - "No"  => False
      - qualquer outra coisa => True (mandatory por segurança)
    """
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
    """
    Retorna (scale, errors)
    scale sempre lista de ints únicos, ordenados
    fallback => [0..5]
    """
    errors = []
    fallback = [0, 1, 2, 3, 4, 5]

    if raw_scale is None:
        return fallback, errors

    if not isinstance(raw_scale, list) or not raw_scale:
        errors.append("Invalid maturity_scale: must be a non-empty array. Falling back to default [0..5].")
        return fallback, errors

    out = []
    for x in raw_scale:
        try:
            out.append(int(x))
        except Exception:
            errors.append(f"Invalid maturity_scale value '{x}': must be integer. Falling back to default [0..5].")
            return fallback, errors

    out = sorted(list(dict.fromkeys(out)))

    bad = [v for v in out if v < 0 or v > 5]
    if bad:
        errors.append(f"Invalid maturity_scale values out of range 0..5: {bad}. Falling back to default [0..5].")
        return fallback, errors

    return out, errors


def _id_natural_key(qid: str):
    """
    Natural sort: extrai números em sequência.
    Ex: Q1, Q10, DG.Q2 etc
    """
    s = str(qid or "")
    nums = re.findall(r"\d+", s)
    if not nums:
        return (10**9, s.lower())
    return (int(nums[0]), s.lower())


def logout():

    from storage.result_storage import load_results

    try:
        get_all_users.clear()
        load_user.clear()
        load_user_by_hash.clear()
        get_all_projects.clear()
        get_projects_for_user.clear()
        load_results.clear()
    except:
        pass

    st.session_state.clear()
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

        if "assessment_messages" not in st.session_state:
            st.session_state.assessment_messages = []

        ensure_started_message()

        if st.session_state.get("assessment_completed"):
            st.success("Assessment completed successfully.")
            return

        # Garantir estado limpo ao entrar
        if "answers" not in st.session_state:
            # Estrutura por domínio:
            # answers = { "domain_0": {"Q1": 3, ...}, "domain_1": {...} }
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

        # ===============================
        # PAGE CONTROLLER
        # ===============================
        page = st.session_state.get("page", "main")

        if page == "account":
            col_a, col_b = st.columns([2, 10])
            with col_a:
                if st.button("⬅ Back", use_container_width=True):
                    st.session_state.page = "main"
                    st.rerun()

            render_account_page(st.session_state)
            return

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
                st.session_state.answers = saved.get("answers", {}) or {}
                st.session_state.dom_idx = int(saved.get("dom_idx", 0))
                st.session_state.q_idx = int(saved.get("q_idx", 0))

                st.session_state.last_saved_snapshot = json.loads(json.dumps(st.session_state.answers))

            st.session_state.loaded_from_storage = True

        # -------------------------
        # INTRO SCREEN
        # -------------------------
        if not st.session_state.get("intro_seen", False):
            render_welcome()
            return

        # -------------------------------------------------
        # LOAD CORE FILES (ANTES DO LAYOUT, PRA NAVEGAÇÃO)
        # -------------------------------------------------
        fs_path = resolve_path(BASE_DIR, "FileSystem_Setup.yaml")
        fs_setup = safe_load(fs_path) or {}
        config = (fs_setup.get("orchestrator_config") or {})

        flow_path = resolve_path(BASE_DIR, config.get("main_flow", "flow.yaml"))
        orch_path = resolve_path(BASE_DIR, config.get("main_orchestration", "default_execution.yaml"))

        flow = safe_load(flow_path) or {}
        orch = safe_load(orch_path) or {}

        req_list = orch.get("execution_request", []) or []
        total_domains = len(req_list)

        if total_domains == 0:
            add_message("No execution_request found in orchestration file.", "error")
            st.stop()

        domain_flow = flow.get("Domain_flow", []) or []

        # -------------------------
        # VALIDATE ORCH PARAMS
        # -------------------------
        # language
        lang_raw = orch.get("language", "Default")
        lang = str(lang_raw or "Default").strip() or "Default"
        if lang.lower() == "default":
            lang = "Default"

        # navigation_mode
        nav_mode_raw = orch.get("navigation_mode", "free")
        nav_mode = _parse_navigation_mode(nav_mode_raw)
        if str(nav_mode_raw or "").strip().lower() not in ("free", "sequential", "seq"):
            add_message(f"Invalid navigation_mode '{nav_mode_raw}'. Using default: FREE.", "warning")
            nav_mode = "free"

        # sort_order
        sort_raw = orch.get("sort_order", "natural")
        sort_order = _parse_sort_order(sort_raw)
        if str(sort_raw or "").strip().lower() not in ("id", "sequential", "natural", "priority"):
            add_message(f"Invalid sort_order '{sort_raw}'. Using default: NATURAL.", "warning")
            sort_order = "natural"

        # maturity_scale
        maturity_scale, scale_errors = _validate_maturity_scale(orch.get("maturity_scale"))
        for e in scale_errors:
            add_message(e, "error")

        # domínio atual
        st.session_state.dom_idx = max(0, min(int(st.session_state.dom_idx), total_domains - 1))
        current_req = req_list[st.session_state.dom_idx]

        # resolve meta do domínio atual
        dom_id = current_req.get("domain")
        dom_meta = next(
            (d for d in domain_flow if str(d.get("domain_id")) == str(dom_id)),
            None
        )
        if not dom_meta:
            add_message(f"Domain metadata not found in flow.yaml for domain_id={dom_id}.", "error")
            st.stop()

        tree_path = resolve_path(
            BASE_DIR,
            f"data/domains/Language/{lang}/{dom_meta['files']['decision_tree']}"
        )

        catalog_path = resolve_path(
            BASE_DIR,
            f"data/domains/Language/{lang}/{dom_meta['files']['action_catalog']}"
        )

        tree_data = safe_load(tree_path) or {}
        catalog_data = safe_load(catalog_path) or {}

        question_block = tree_data.get("questions", {}) or {}
        question_block = {str(k).lower(): v for k, v in question_block.items()}

        selected_questions = current_req.get("selected_questions", []) or []

        # sort_order:
        # - NATURAL => como veio no YAML
        # - ID => ordenar Q1..Q10..
        if sort_order == "id":
            selected_questions = sorted(selected_questions, key=lambda q: _id_natural_key(q.get("id")))

        total_q_current_domain = len(selected_questions)
        if total_q_current_domain == 0:
            add_message(f"No selected_questions for domain {dom_id}.", "error")
            st.stop()

        # clamp q_idx
        st.session_state.q_idx = max(0, min(int(st.session_state.q_idx), total_q_current_domain - 1))

        # questão atual
        q_plan = selected_questions[st.session_state.q_idx]
        q_id = q_plan.get("id")
        q_key = str(q_id).lower()

        if q_key not in question_block:
            add_message(f"Question {q_id} not found.", "error")
            st.stop()

        q_content = question_block[q_key] or {}

        # mandatory
        is_mandatory = _normalize_bool_yesno(q_plan.get("mandatory", None), default_if_unknown=True)

        # domínio scope para respostas
        domain_key = f"domain_{st.session_state.dom_idx}"
        if domain_key not in st.session_state.answers:
            st.session_state.answers[domain_key] = {}

        # ===============================
        # LAYOUT
        # ===============================
        st.markdown("""
        <style>
          .dmx-small { font-family: Arial, sans-serif; font-size: 8px; line-height: 1.25; }
          .dmx-tree-item button { padding-top: 2px !important; padding-bottom: 2px !important; }
          div[data-testid="stButton"] > button { border-radius: 8px; }
        </style>
        """, unsafe_allow_html=True)

        col_left, col_main = st.columns([2, 6], gap="small")

        # -------------------------
        # LEFT PANEL (Tree + Messages)
        # -------------------------
        with col_left:

            nav_box = st.container(border=True)
            with nav_box:
                st.markdown("**Navigation**")

                # Scroll area (tree)
                with st.container(height=320):

                    for i, r in enumerate(req_list):
                        dom_id_i = r.get("domain")
                        meta = next((d for d in domain_flow if str(d.get("domain_id")) == str(dom_id_i)), {}) or {}
                        acr = (meta.get("acronym") or f"D{dom_id_i}").strip()
                        name = (meta.get("name") or "").strip()

                        label = f"{acr}"
                        #if name:
                        #    label = f"{acr}  ·  {name}"

                        expanded = (i == st.session_state.dom_idx)

                        with st.expander(label, expanded=expanded):
                            # Abrir domínio
                            #if st.button("Open domain", key=f"tree_open_dom_{i}", use_container_width=True):
                            #    st.session_state.dom_idx = i
                            #    st.session_state.q_idx = 0
                            #    st.rerun()

                            # Questões do domínio
                            sq = r.get("selected_questions", []) or []
                            if sort_order == "id":
                                sq = sorted(sq, key=lambda q: _id_natural_key(q.get("id")))

                            qids = [q.get("id") for q in sq if q.get("id")]

                            for qi, qx in enumerate(qids):
                                prefix = "▸ " if (i == st.session_state.dom_idx and qi == st.session_state.q_idx) else "  "
                                if st.button(f"{prefix}{qx}", key=f"tree_q_{i}_{qi}", use_container_width=True):
                                    st.session_state.dom_idx = i
                                    st.session_state.q_idx = qi
                                    st.rerun()

            msg_box = st.container(border=True)
            with msg_box:
                st.markdown("**Messages**")
                msgs = get_messages()

                with st.container(height=260):
                    if not msgs:
                        st.markdown("<div class='dmx-small'>No messages.</div>", unsafe_allow_html=True)
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

        # -------------------------
        # MAIN PANEL
        # -------------------------
        with col_main:

            col_title, col_menu = st.columns([12, 1])

            with col_title:
                title_acr = (dom_meta.get("acronym") or "").strip()
                title_name = (dom_meta.get("name") or "Domain").strip()
                if title_acr:
                    st.header(f"{title_acr} · {title_name}")
                else:
                    st.header(title_name)

            # =========================
            # QUESTION TEXT (compatível com YAML atual e antigo)
            # =========================
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
                st.caption(f"Objective: {q_obj}")

            with col_menu:
                with st.popover("⋮"):

                    st.markdown("### Menu")

                    if st.button("👤 User / Account", use_container_width=True):
                        st.session_state.page = "account"
                        st.rerun()

                    if st.button("🚪 Log off", key="menu_logoff", use_container_width=True):
                        logout()

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
            # LIKERT SCALE (DYNAMIC maturity_scale)
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

            current_answer = (
                st.session_state.answers
                .get(domain_key, {})
                .get(q_id)
            )

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
            if q_id in st.session_state.answers.get(domain_key, {}):
                score = st.session_state.answers[domain_key][q_id]

                mapping = q_content.get("score_action_mapping") or {}
                if score not in mapping:
                    add_message(f"Missing score_action_mapping for score {score} in question {q_id}.", "error")
                else:
                    action_code = mapping[score].get("action_code")
                    action = (catalog_data.get("action_catalog", {}) or {}).get(action_code)

                    header_color = LIKERT.get(score, ("", "", "#666"))[2]

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

                        allowed_procs = q_plan.get("procedures", []) or []

                        for proc in action.get("procedures", []):
                            if proc.get("number") in allowed_procs:
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
            # SAVE + NAVIGATION
            # -------------------------------------------------
            total_q = len(selected_questions)

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

                        st.session_state.last_saved_snapshot = json.loads(json.dumps(st.session_state.answers))
                        add_message("Progress saved successfully.", "success")
                        st.rerun()

            # PREVIOUS (ENTRE DOMÍNIOS)
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

            # NEXT (mandatory enforcement + final validation)
            with col_next:

                answered = (current_answer is not None)
                next_disabled = (not answered) if is_mandatory else False

                if st.button(
                    "➡ Next",
                    use_container_width=True,
                    disabled=next_disabled
                ):
                    if is_mandatory and current_answer is None:
                        add_message(f"Mandatory question not answered: {dom_meta.get('acronym','')} / {q_id}.", "error")
                        st.rerun()

                    at_last_q = (st.session_state.q_idx >= (total_q_current_domain - 1))
                    at_last_domain = (st.session_state.dom_idx >= (total_domains - 1))

                    if at_last_q and at_last_domain:
                        missing = []

                        for d_index, req in enumerate(req_list):
                            dom_id_i = req.get("domain")
                            meta_i = next((d for d in domain_flow if str(d.get("domain_id")) == str(dom_id_i)), {}) or {}
                            dom_label = (meta_i.get("acronym") or meta_i.get("name") or f"Domain {dom_id_i}").strip()

                            sq = req.get("selected_questions", []) or []
                            if sort_order == "id":
                                sq = sorted(sq, key=lambda q: _id_natural_key(q.get("id")))

                            dk = f"domain_{d_index}"
                            ans_d = st.session_state.answers.get(dk, {}) or {}

                            for q in sq:
                                qid = q.get("id")
                                if not qid:
                                    continue
                                mand = _normalize_bool_yesno(q.get("mandatory", None), default_if_unknown=True)
                                if mand and qid not in ans_d:
                                    missing.append((dom_label, qid))

                        if missing:
                            add_message("Assessment cannot be completed. Missing mandatory answers:", "error")
                            for dom_label, qid in missing:
                                add_message(f"{dom_label}: {qid}", "error")
                            st.rerun()

                    advance_flow(total_q_current_domain, total_domains)

    except Exception as e:
        add_message(f"Renderer error: {e}", "error")
        st.exception(e)
