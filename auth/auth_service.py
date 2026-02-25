import os
import re
import time
import pycountry
import shutil
import streamlit as st
import hashlib

from auth.email_service import send_email
from core.config import APP_TITLE, refresh_runtime_config, BASE_DIR
from storage.project_storage import get_all_projects, get_projects
from storage.user_project_storage import get_projects_for_user
from storage.user_storage import load_user, save_user, verify_password, get_all_users, load_user_by_hash


from data.repository_factory import get_repository

repo = get_repository()

# =========================================================
# Finished project
# =========================================================
def has_finished_project(user_id, project_id):

    rows = repo.fetch_all("finished_assessments")

    for r in rows:

        same_user = str(r.get("user_id", "")).strip() == str(user_id).strip()
        same_project = str(r.get("project_id", "")).strip() == str(project_id).strip()

        finished_raw = r.get("is_finished")

        if isinstance(finished_raw, bool):
            is_finished = finished_raw
        elif isinstance(finished_raw, (int, float)):
            is_finished = finished_raw == 1
        elif isinstance(finished_raw, str):
            is_finished = finished_raw.strip().lower() in ["true", "1", "yes"]
        else:
            is_finished = False

        if same_user and same_project and is_finished:
            return True

    return False


# =========================================================
# Countries
# =========================================================
def get_countries():
    countries = []
    for country in pycountry.countries:
        code = country.alpha_2
        name = country.name
        flag = "".join(chr(127397 + ord(c)) for c in code)
        countries.append(f"{flag} {name} ({code})")
    countries.sort()
    return countries


# =========================================================
# ENV
# =========================================================
def get_env(name: str):
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return os.getenv(name)


ADMINS_RAW = get_env("ADMINS") or ""

if isinstance(ADMINS_RAW, list):
    ADMINS = {x.strip().lower() for x in ADMINS_RAW if x.strip()}
else:
    ADMINS = {x.strip().lower() for x in str(ADMINS_RAW).split(",") if x.strip()}

# =========================================================
# FLASH
# =========================================================
def _flash_set(msg: str, level: str = "info"):
    st.session_state._flash = {"msg": msg, "level": level, "ts": time.time()}


def _flash_render(ttl_seconds: int = 3):
    data = st.session_state.get("_flash")
    if not data:
        return

    if time.time() - data.get("ts", 0) > ttl_seconds:
        st.session_state.pop("_flash", None)
        return

    level = data.get("level", "info")
    msg = data.get("msg", "")

    if level == "error":
        st.error(msg)
    elif level == "success":
        st.success(msg)
    elif level == "warning":
        st.warning(msg)
    else:
        st.info(msg)


# =========================================================
# CONTROLLER
# =========================================================
def render_auth():
    if "app_mode" not in st.session_state:
        st.session_state.app_mode = "login"

    if st.session_state.app_mode == "login":
        render_login()
    elif st.session_state.app_mode == "register":
        render_register()
    elif st.session_state.app_mode == "select_project":
        render_project_selection()


# =========================================================
# LOGIN
# =========================================================
def render_login():
    left, center, right = st.columns([1, 3, 1]) 
  
    with center:
        st.markdown(
            f"<h3 style='text-align:center;'>{APP_TITLE}</h3>",
            unsafe_allow_html=True,
        )        
        st.markdown(st._html_tr("<h3 style='text-align:center;'>Login</h3>"), unsafe_allow_html=True)

        _flash_render()

        email = st.text_input("Email")
        password = st.text_input("Password", type="password")

        if st.button("Login", use_container_width=True):

            from storage.project_storage import (
                get_projects,
                create_project,
            )
            import os
            from core.config import BASE_DIR

            user = load_user(email)            

            if not user or not verify_password(password, user["password_hash"]):
                _flash_set("User does not exist or password is incorrect.", "error")
                st.rerun()
            
            # chave real do sistema
            user_id = str(user.get("email_hash") or "").strip()
            st.session_state.user_id = user_id

            # gera hash dos admins definidos no .env
            admin_hashes = {
                hashlib.sha256(x.strip().lower().encode()).hexdigest()
                for x in ADMINS
            }
                 

            st.session_state.is_admin = user_id in admin_hashes

            projects = get_projects() or []
            

            base_projects_dir = os.path.join(BASE_DIR, "data", "projects")

            # -------------------------------------------------
            # CASE 1 — NO PROJECTS IN DB
            # -------------------------------------------------
            if len(projects) == 0:

                create_project(
                    name="DEMO",
                    created_by=st.session_state.user_id,
                    allow_open_access=True,
                )

                st.session_state._temp_user = user
                st.session_state.app_mode = "select_project"
                st.rerun()

            # -------------------------------------------------
            # CASE 2 — PROJECTS EXIST BUT NO FOLDERS
            # -------------------------------------------------
            any_valid_structure = False

            for p in projects:
                pid = str(p.get("project_id")).strip()
                project_root = os.path.join(base_projects_dir, pid)
                general_dir = os.path.join(project_root, "General")

                if os.path.isdir(general_dir):
                    any_valid_structure = True
                    break

            if not any_valid_structure:

                for p in projects:
                    pid = str(p.get("project_id")).strip()
                    project_root = os.path.join(base_projects_dir, pid)
                    general_dir = os.path.join(project_root, "General")

                    if not os.path.isdir(general_dir):

                        # Rebuild folder structure only (without reinserting DB)
                        os.makedirs(project_root, exist_ok=True)

                        # reutiliza create_project lógica de cópia
                        # mas sem criar novo registro                        
                        locale = st.session_state.get("locale", "us")
                        domains_src = os.path.join(BASE_DIR, "data", "domains", "language", locale)
                        
                        general_src = os.path.join(BASE_DIR, "data", "general")

                        domains_dest = os.path.join(project_root, "Domains")
                        general_dest = os.path.join(project_root, "General")

                        os.makedirs(domains_dest, exist_ok=True)
                        os.makedirs(general_dest, exist_ok=True)

                        for item in os.listdir(domains_src):
                            s = os.path.join(domains_src, item)
                            d = os.path.join(domains_dest, item)
                            if os.path.isdir(s):
                                shutil.copytree(s, d, dirs_exist_ok=True)
                            else:
                                shutil.copy2(s, d)

                        for item in os.listdir(general_src):
                            s = os.path.join(general_src, item)
                            d = os.path.join(general_dest, item)
                            if os.path.isdir(s):
                                shutil.copytree(s, d, dirs_exist_ok=True)
                            else:
                                shutil.copy2(s, d)

                        fs_src = os.path.join(BASE_DIR, "filesystem_setup.yaml")

                        if os.path.isfile(fs_src):
                            shutil.copy2(fs_src, os.path.join(project_root, "FileSystem_Setup.yaml"))

                            general_fs_dest = os.path.join(project_root, "General", "FileSystem_Setup.yaml")
                            os.makedirs(os.path.dirname(general_fs_dest), exist_ok=True)
                            shutil.copy2(fs_src, general_fs_dest)

                st.session_state._temp_user = user
                st.session_state.app_mode = "select_project"
                st.rerun()

            # -------------------------------------------------
            # NORMAL FLOW
            # -------------------------------------------------
            st.session_state._temp_user = user
            st.session_state.app_mode = "select_project"
            st.rerun()

        if st.button("Create Account", use_container_width=True):

            if not email or not re.match(r"[^@]+@[^@]+\.[^@]+", email):
                _flash_set("Enter a valid email first.", "error")
                st.rerun()

            if load_user(email):
                _flash_set("This email already exists. Please login.", "error")
                st.rerun()

            st.session_state.register_prefill_email = email.strip()
            st.session_state.app_mode = "register"
            st.rerun()


# =========================================================
# REGISTER
# =========================================================
def render_register():
    left, center, right = st.columns([1, 4, 1])

    if "_register_pending" not in st.session_state:
        st.session_state._register_pending = False
    if "_register_payload" not in st.session_state:
        st.session_state._register_payload = None

    with center:
        st.markdown(
            f"<h3 style='text-align:center;'>{APP_TITLE}</h3>",
            unsafe_allow_html=True,
        )        
        st.markdown(st._html_tr("<h4 style='text-align:center;'>Create Account</h4>"), unsafe_allow_html=True)
        st.caption("* Required fields")

        error_box = st.empty()
        prefill_email = st.session_state.get("register_prefill_email", "")

        full_name = st.text_input("Full Name *")
        email = st.text_input("Email *", value=prefill_email)
        password = st.text_input("Password *", type="password")
        confirm_password = st.text_input("Confirm Password *", type="password")

        company = st.text_input("Company")
        department = st.text_input("Department")
        job_title = st.text_input("Job Title")
        phone = st.text_input("Phone")

        countries = get_countries()
        selected_country = st.selectbox("Country *", countries, index=None)

        state_province = st.text_input("State/Province")
        city = st.text_input("City")

        consent = st.checkbox("I consent to the use of my personal data for DOMMx *")

        col_save, col_back = st.columns(2)

        # Execução do save em rerun, para bloquear cliques múltiplos
        if st.session_state._register_pending and st.session_state._register_payload:
            with st.spinner("Saving user..."):
                try:
                    payload = st.session_state._register_payload

                    created = save_user(
                        email=payload["email"],
                        password=payload["password"],
                        full_name=payload["full_name"],
                        company=payload["company"],
                        department=payload["department"],
                        job_title=payload["job_title"],
                        phone=payload["phone"],
                        country=payload["country"],
                        state_province=payload["state_province"],
                        city=payload["city"],
                        consent=True,
                    )

                    admin_email = get_env("SMTP_USER")
                    if admin_email:
                        try:
                            send_email(
                                admin_email,
                                "New User Registration",
                                f"New user created: {payload['email']}"
                            )
                        except Exception:
                            pass

                    try:
                        get_all_users.clear()
                        load_user.clear()
                    except Exception:
                        pass

                    if created:
                        st.session_state.pop("register_prefill_email", None)
                        _flash_set("User created successfully. Please login.", "success")

                        # primeiro user deve ser admin
                        if payload.get("is_first_user"):
                            st.session_state.bootstrap_admin = True
                            st.session_state.bootstrap_admin_email = payload.get("email_norm")

                        st.session_state.app_mode = "login"
                    else:
                        error_box.error("User already exists.")

                except Exception as e:
                    error_box.error(str(e))

                finally:
                    st.session_state._register_pending = False
                    st.session_state._register_payload = None
                    st.rerun()

        with col_save:
            if st.button("Save", use_container_width=True, disabled=st.session_state._register_pending):

                errors = []

                if not full_name.strip():
                    errors.append("Full Name is required.")
                if not email.strip():
                    errors.append("Email is required.")
                elif not re.match(r"[^@]+@[^@]+\.[^@]+", email.strip()):
                    errors.append("Invalid email format.")
                if not selected_country:
                    errors.append("Country is required.")
                if not consent:
                    errors.append("Consent is required.")
                if len(password) < 8:
                    errors.append("Password must be at least 8 characters.")
                if password != confirm_password:
                    errors.append("Passwords do not match.")
                if load_user(email.strip()):
                    errors.append("User already exists.")

                # -------------------------------------------------
                # FIRST USER MUST BE ADMIN
                # -------------------------------------------------
                existing_users = get_all_users() or []
                is_first_user = (len(existing_users) == 0)

                email_norm = email.strip().lower()

                if is_first_user and (email_norm not in [x.lower() for x in ADMINS]):
                    errors.append("Initial setup: only an admin email can create the first user.")

                if errors:
                    error_box.error("\n".join(errors))
                else:
                    st.session_state._register_pending = True
                    st.session_state._register_payload = {
                        "email": email.strip(),
                        "password": password,
                        "full_name": full_name.strip(),
                        "company": company.strip(),
                        "department": department.strip(),
                        "job_title": job_title.strip(),
                        "phone": phone.strip(),
                        "country": selected_country,
                        "state_province": state_province.strip(),
                        "city": city.strip(),
                        "is_first_user": is_first_user,
                        "email_norm": email_norm,
                    }
                    st.rerun()

        with col_back:
            if st.button("Back", use_container_width=True, disabled=st.session_state._register_pending):
                st.session_state.app_mode = "login"
                st.rerun()


# =========================================================
# PROJECT SELECTION
# =========================================================
def render_project_selection():

    user = st.session_state._temp_user
    user_id = user["email_hash"]

    all_projects = get_all_projects()
    user_projects = get_projects_for_user(user_id) or []

    active_projects = []
    for p in all_projects:
        raw_active = p.get("is_active", True)

        if isinstance(raw_active, bool):
            active_value = raw_active
        else:
            active_value = str(raw_active).strip().lower() == "true"

        if active_value:
            active_projects.append(p)

    filtered_projects = []

    for p in active_projects:

        is_associated = p["project_id"] in user_projects

        raw_open = p.get("allow_open_access", False)
        if isinstance(raw_open, bool):
            allow_open = raw_open
        else:
            allow_open = str(raw_open).strip().lower() == "true"

        if is_associated or allow_open:
            filtered_projects.append(p)

    left, center, right = st.columns([1, 3, 1])

    with center:
        st.markdown(
            st._html_tr(f"<h3 style='text-align:center;'>{APP_TITLE}</h3>"),
            unsafe_allow_html=True,
        )

        st.subheader("Select Project")

        if not filtered_projects:
            st.warning("No available projects for your user.")
            if st.button("Back to Login", use_container_width=True):
                st.session_state.app_mode = "login"
                st.session_state.pop("_temp_user", None)
                st.rerun()
            return

        project_map = {
            p["project_id"]: p["name"]
            for p in filtered_projects
        }

        selected_project = st.selectbox(
            "Project",
            options=list(project_map.keys()),
            format_func=lambda x: project_map.get(x, x),
        )

        selected_project_obj = next(
            (p for p in filtered_projects if p["project_id"] == selected_project),
            {}
        )

        raw_open = selected_project_obj.get("allow_open_access", False)
        if isinstance(raw_open, bool):
            allow_open = raw_open
        else:
            allow_open = str(raw_open).strip().lower() == "true"
            
        
        has_access = selected_project in user_projects

        # -------------------------------------------------
        # FINISHED PROJECT -> SHOW REPORT + BACK, DO NOT ENTER
        # -------------------------------------------------
        if selected_project and has_finished_project(user_id, selected_project):

            st.success("You have already completed all actions for this project.")

            # CSS: mesmos tamanhos e altura
            st.markdown(
                """
                <style>
                div[data-testid="stButton"] > button,
                div[data-testid="stDownloadButton"] > button {
                    height: 55px !important;
                    border-radius: 8px !important;
                }
                </style>
                """,
                unsafe_allow_html=True
            )

            # PDF placeholder (vazio/mini)
            import io
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.lib.pagesizes import A4

            buffer = io.BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4)
            styles = getSampleStyleSheet()

            elements = [
                Paragraph("DOMMx Final Assessment Report", styles["Heading1"]),
                Spacer(1, 20),
                Paragraph("Placeholder PDF (test).", styles["Normal"]),
            ]
            doc.build(elements)

            pdf = buffer.getvalue()
            buffer.close()

            col_r1, col_r2 = st.columns(2)

            with col_r1:
                st.download_button(
                    label="📄 Download Final Report",
                    data=pdf,
                    file_name="DOMMx_Final_Report.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )

            with col_r2:
                if st.button("↩ Back to Login", use_container_width=True):
                    st.session_state.app_mode = "login"
                    st.session_state.pop("_temp_user", None)
                    st.rerun()

            return
        
        col_enter, col_request = st.columns(2)

        with col_enter:
            if st.button(
                "Enter",
                use_container_width=True,
                disabled=not (has_access or allow_open),
            ):                

                # 🔥 NORMAL FLOW (only if not finished)
                st.session_state.user_id = user_id
                st.session_state.active_project = selected_project

                st.session_state.project_root = os.path.join(
                    BASE_DIR,
                    "data",
                    "projects",
                    str(selected_project)
                )
                
                # -------------------------------------------------
                # MULTI-TENANT PROJECT CONTEXT
                # -------------------------------------------------
                project_root = os.path.join(BASE_DIR, "data", "projects", str(selected_project).strip())
                general_dir = os.path.join(project_root, "General")

                if not os.path.isdir(general_dir):
                    st.session_state.project_config_error = True
                    st.session_state.project_config_error_msg = (
                        "Project configuration directory does not exist:\n"
                        f"{general_dir}\n\n"
                        "You will be logged out automatically."
                    )
                    st.session_state.logout_at = time.time() + 4
                    st.session_state.app_mode = "app"
                    st.session_state.pop("_temp_user", None)
                    st.rerun()

                st.session_state.project_root = project_root

                # reset do assessment ao trocar de projeto
                for k in [
                    "answers",
                    "dom_idx",
                    "q_idx",
                    "loaded_from_storage",
                    "last_saved_snapshot",
                    "last_save_ts",
                    "assessment_completed",
                    "assessment_messages",
                    "_assessment_started_msg",
                    "intro_seen",
                ]:
                    if k in st.session_state:
                        del st.session_state[k]

                # recarrega app_config do projeto
                refresh_runtime_config()                
                
                # força revalidação no próximo ciclo
                st.session_state.pop("locale", None)

                current_user = load_user_by_hash(st.session_state.get("user_id"))
                user_email = current_user.get("email") if current_user else None
                
                # bootstrap admin: ao entrar, abre modal de projetos (setup inicial)
                if st.session_state.get("bootstrap_admin") and st.session_state.get("bootstrap_admin_email") == user_email:
                    st.session_state.open_dialog = "projects"
                    st.session_state.bootstrap_admin = False

                st.session_state.app_mode = "app"
                st.session_state.pop("_temp_user", None)
                st.rerun()

        with col_request:
            if not has_access and not allow_open:
                if st.button("Request Access", use_container_width=True):
                    admin_email = get_env("SMTP_USER")
                    if admin_email:
                        send_email(
                            admin_email,
                            "Project Access Request",
                            f"User: {user.get('email','')}\nRequested Project: {project_map.get(selected_project)}"
                        )
                    st.session_state.app_mode = "login"
                    st.session_state.pop("_temp_user", None)
                    st.rerun()
