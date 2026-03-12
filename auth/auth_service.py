import os
import re
import time
import secrets
import datetime
import pycountry
import shutil
import streamlit as st
import streamlit.components.v1 as components
import hashlib
import base64

from auth.email_service import send_email
from core.config import APP_TITLE, refresh_runtime_config, BASE_DIR
from storage.project_storage import get_all_projects, get_projects
from storage.user_project_storage import get_projects_for_user
from storage.user_storage import load_user, save_user, verify_password, get_all_users, load_user_by_hash

from core.ai_report_service import AIReportService
from data.repository_factory import get_repository
from core.config import BASE_DIR

from urllib.parse import quote, unquote

import traceback

repo = get_repository()




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
# reset password token
# =========================================================


def create_password_reset_token(email_hash):

    expires = int(time.time()) + 1800  # 30 min

    payload = f"{email_hash}|{expires}"
    signature = hashlib.sha256(payload.encode()).hexdigest()

    token = f"{payload}|{signature}"

    return token
    
def parse_password_reset_token(token):

    try:
        token = unquote(str(token).strip())

        email_hash, expires, signature = token.split("|")

        payload = f"{email_hash}|{expires}"
        expected_signature = hashlib.sha256(payload.encode()).hexdigest()

        if signature != expected_signature:
            return None

        if int(time.time()) > int(expires):
            return None

        return {
            "email_hash": email_hash,
            "expires": int(expires)
        }

    except Exception:
        return None  
    
    
def render_forgot_password():

    if "_sending_reset" not in st.session_state:
        st.session_state["_sending_reset"] = False

    left, center, right = st.columns([1, 5, 1])

    with center:

        st.markdown(
            st._html_tr("<h3 style='text-align:center;'>Forgot Password</h3>"),
            unsafe_allow_html=True
        )

        if "_forgot_status" not in st.session_state:
            st.session_state["_forgot_status"] = None

        status = st.session_state.get("_forgot_status")

        if status:
            level = status.get("level")
            msg = status.get("msg", "")

            if level == "success":
                st.success(msg)
            elif level == "error":
                st.error(msg)
            else:
                st.info(msg)

        success_ts = st.session_state.get("_forgot_success_ts")

        if success_ts:
            if time.time() - success_ts > 3:
                st.session_state.pop("_forgot_success_ts", None)
                st.session_state.pop("_forgot_status", None)
                st.session_state["app_mode"] = "login"
                st.rerun()

        if "forgot_email_input" not in st.session_state:
            st.session_state["forgot_email_input"] = st.session_state.get("recover_email", "")

        email = st.text_input(
            "Email",
            key="forgot_email_input"
        )

        send_clicked = st.button(
            "Send Reset Link",
            use_container_width=True,
            disabled=st.session_state["_sending_reset"]
        )

        if send_clicked:

            st.session_state["_sending_reset"] = True
            st.rerun()

        if st.session_state["_sending_reset"]:

            try:

                if not email:
                    st.error("Enter your email.")
                    st.session_state["_sending_reset"] = False
                    return

                user = load_user(email)

                if not user:
                    st.success("If this email exists, a reset link was sent.")
                    st.session_state["_sending_reset"] = False
                    return

                token = create_password_reset_token(user["email_hash"])

                app_url = get_env("APP_URL_PROD") or get_env("APP_URL_LOCAL")

                if not app_url:
                    st.error("APP_URL not configured.")
                    st.session_state["_sending_reset"] = False
                    return

                encoded_token = quote(token, safe="")
                reset_link = f"{app_url}?reset_token={encoded_token}"

                with st.spinner("Sending reset email..."):

                    send_email(
                        email,
                        "Password Reset",
                        f"Click the link to reset your password:\n\n{reset_link}"
                    )

                st.session_state["_forgot_success_ts"] = time.time()

                st.session_state["_forgot_status"] = {
                    "level": "success",
                    "msg": "Reset link sent. Please check your email."
                }

                st.session_state["_sending_reset"] = False
                st.rerun()

            except Exception:
                st.error("Error sending reset email.")
                st.session_state["_sending_reset"] = False

        if st.button(
            "Back",
            use_container_width=True,
            disabled=st.session_state["_sending_reset"]
        ):
            st.session_state["_forgot_status"] = None
            st.session_state["app_mode"] = "login"
            st.rerun()
    

def render_reset_password():

    if "_updating_password" not in st.session_state:
        st.session_state["_updating_password"] = False

    token = st.session_state.get("reset_token")

    record = parse_password_reset_token(token)

    if not record:
        st.error("Invalid or expired reset link.")
        if st.button(
            "Login",
            use_container_width=True,
            key="btn_back_login_from_reset_invalid"
        ):
            st.session_state.pop("reset_token", None)

            try:
                st.query_params.clear()
            except Exception:
                pass

            st.session_state["app_mode"] = "login"
            st.rerun()
        return

    email_hash = str(record["email_hash"]).strip()

    left, center, right = st.columns([1, 4, 1])

    with center:

        st.markdown(
            st._html_tr("<h3 style='text-align:center;'>Reset Password</h3>"),
            unsafe_allow_html=True
        )

        if st.session_state.get("_reset_done"):
            st.success("Password updated successfully.")

            if st.button(
                "Login",
                use_container_width=True,
                key="btn_back_login_from_reset_success"
            ):
                st.session_state.pop("reset_token", None)
                st.session_state.pop("_reset_done", None)

                try:
                    st.query_params.clear()
                except Exception:
                    pass

                st.session_state["app_mode"] = "login"
                st.rerun()

            return

        new_password = st.text_input(
            "New Password",
            type="password",
            key="reset_new_password"
        )

        confirm = st.text_input(
            "Confirm Password",
            type="password",
            key="reset_confirm_password"
        )

        update_clicked = st.button(
            "Update Password",
            use_container_width=True,
            key="btn_update_password",
            disabled=st.session_state["_updating_password"]
        )

        if update_clicked:
            st.session_state["_updating_password"] = True
            st.rerun()

        if st.session_state["_updating_password"]:

            if not new_password:
                st.error("Enter a password.")
                st.session_state["_updating_password"] = False
                return

            if new_password != confirm:
                st.error("Passwords do not match.")
                st.session_state["_updating_password"] = False
                return

            if len(new_password) < 8:
                st.error("Password must be at least 8 characters.")
                st.session_state["_updating_password"] = False
                return

            try:

                with st.spinner("Updating password..."):

                    user = load_user_by_hash(email_hash)

                    if not user:
                        st.error("User not found.")
                        st.session_state["_updating_password"] = False
                        return

                    save_user(
                        email=user["email"],
                        password=new_password,
                        full_name=user.get("full_name", ""),
                        company=user.get("company", ""),
                        department=user.get("department", ""),
                        job_title=user.get("job_title", ""),
                        phone=user.get("phone", ""),
                        country=user.get("country", ""),
                        state_province=user.get("state_province", ""),
                        city=user.get("city", ""),
                        consent=user.get("consent", False),
                    )

                try:
                    load_user.clear()
                    load_user_by_hash.clear()
                    get_all_users.clear()
                except Exception:
                    pass

            except Exception as e:
                st.error(str(e))
                st.session_state["_updating_password"] = False
                return

            st.session_state["_updating_password"] = False
            st.session_state["_reset_done"] = True
            st.rerun()

        if st.button(
            "Login",
            use_container_width=True,
            key="btn_back_login_from_reset",
            disabled=st.session_state["_updating_password"]
        ):

            st.session_state.pop("reset_token", None)
            st.session_state.pop("_reset_done", None)

            try:
                st.query_params.clear()
            except Exception:
                pass

            st.session_state["app_mode"] = "login"

            st.rerun()
    
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
        
    # -------------------------------------------------
    # INIT MODE
    # -------------------------------------------------
    if "app_mode" not in st.session_state:
        st.session_state["app_mode"] = "login"
        
    mode = st.session_state.get("app_mode")

    # -------------------------------------------------
    # PRIORIDADE PARA ESTADO INTERNO
    # -------------------------------------------------
    if mode == "forgot":
        return render_forgot_password()

    if mode == "reset_password":
        return render_reset_password()

    if mode == "register":
        return render_register()

    if mode == "select_project":
        return render_project_selection()

    # -------------------------------------------------
    # QUERY PARAM RESET TOKEN
    # -------------------------------------------------
    token = None

    try:
        params = st.query_params

        token_param = params.get("reset_token", None)

        if isinstance(token_param, list):
            token_param = token_param[0]

        if token_param:
            token = str(token_param).strip()

    except Exception:
        token = None

    # primeiro acesso ao link de reset
    if token:
        st.session_state["reset_token"] = token
        st.session_state["app_mode"] = "reset_password"
        return render_reset_password()

    # -------------------------------------------------
    # DEFAULT
    # -------------------------------------------------
    return render_login()
    
# =========================================================
# LOGIN
# =========================================================
def render_login():
        
    left, center, right = st.columns([1, 3, 1]) 

    with center:

        st.markdown(st._html_tr(
            f"<h3 style='text-align:center;'>{APP_TITLE}</h3>"),
            unsafe_allow_html=True,
        )

        st.markdown(
            st._html_tr("<h3 style='text-align:center;'>Login</h3>"),
            unsafe_allow_html=True
        )

        _flash_render()

        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")

        email_valid = bool(email and "@" in email)
        login_enabled = email_valid and bool(password)
        forgot_enabled = email_valid
        create_enabled = email_valid

        # -------------------------------------------------
        # LOGIN
        # -------------------------------------------------
        if st.button(
            "Login",
            use_container_width=True,
            disabled=not login_enabled,
            key="btn_login_main"
        ):

            from storage.project_storage import (
                get_projects,
                create_project,
            )

            import os
            from core.config import BASE_DIR

            try:
                user = load_user(email)
            except Exception as e:
                st.error(f"Erro real: {e}")
                raise

            if not user or not verify_password(password, user["password_hash"]):

                st.session_state.pop("login_password", None)

                st.session_state._flash = {
                    "msg": "User does not exist or password is incorrect. You can create a new account.",
                    "level": "error",
                    "ts": time.time()
                }

                st.rerun()

            user_id = str(user.get("email_hash") or "").strip()
            st.session_state.user_id = user_id

            admin_hashes = {
                hashlib.sha256(x.strip().lower().encode()).hexdigest()
                for x in ADMINS
            }

            st.session_state.is_admin = user_id in admin_hashes

            projects = get_projects() or []

            base_projects_dir = os.path.join(BASE_DIR, "data", "projects")

            # -------------------------------------------------
            # CASE 1 — NO PROJECTS
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
            # CASE 2 — PROJECTS WITHOUT STRUCTURE
            # -------------------------------------------------
            any_valid_structure = False

            for p in projects:
                pid = str(p.get("project_id")).strip()
                project_root = os.path.join(base_projects_dir, pid)
                general_dir = os.path.join(project_root, "general")

                if os.path.isdir(general_dir):
                    any_valid_structure = True
                    break

            if not any_valid_structure:

                for p in projects:

                    pid = str(p.get("project_id")).strip()
                    project_root = os.path.join(base_projects_dir, pid)
                    general_dir = os.path.join(project_root, "general")

                    if not os.path.isdir(general_dir):

                        os.makedirs(project_root, exist_ok=True)

                        locale = st.session_state.get("locale", "us")

                        domains_src = os.path.join(
                            BASE_DIR,
                            "data",
                            "domains",
                            "language",
                            locale
                        )

                        general_src = os.path.join(BASE_DIR, "data", "general")

                        domains_dest = os.path.join(project_root, "domains")
                        general_dest = os.path.join(project_root, "general")

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

                            shutil.copy2(
                                fs_src,
                                os.path.join(project_root, "FileSystem_Setup.yaml")
                            )

                            general_fs_dest = os.path.join(
                                project_root,
                                "general",
                                "FileSystem_Setup.yaml"
                            )

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

        # -------------------------------------------------
        # FORGOT PASSWORD
        # -------------------------------------------------
        if st.button(
            "Forgot Password",
            use_container_width=True,
            disabled=not forgot_enabled,
            key="btn_forgot_password_main"
        ):

            st.session_state["recover_email"] = email.strip()
            st.session_state["app_mode"] = "forgot"
            #return render_forgot_password()
            st.rerun()
            
        # -------------------------------------------------
        # CREATE ACCOUNT
        # -------------------------------------------------
        if st.button(
            "Create Account",
            use_container_width=True,
            disabled=not create_enabled,
            key="btn_create_account_main"
        ):

            try:
                existing_user = load_user(email)
            except Exception as e:
                st.error(f"Erro real: {e}")
                raise

            if existing_user:
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

        # -------------------------
        # CONSENT TERM (real file link, Chrome safe)
        # -------------------------
        consent_pdf_path = os.path.join(
            BASE_DIR,
            "data",
            "general",
            "Consentimento_Informado_Focus_Group_DOMMx.pdf"
        )

        if "consent_term_opened" not in st.session_state:
            st.session_state.consent_term_opened = False

        # ALWAYS initialize and load bytes (needed for blob open)
        pdf_bytes = None
        pdf_exists = os.path.isfile(consent_pdf_path)

        if pdf_exists:
            try:
                with open(consent_pdf_path, "rb") as f:
                    pdf_bytes = f.read()
            except Exception:
                pdf_bytes = None
                pdf_exists = False

        col_term_a, col_term_b = st.columns([1, 1])

        with col_term_a:
            if st.button("📄 Open Consent Term", key="btn_open_consent_term", use_container_width=True):

                if pdf_bytes:
                    b64 = base64.b64encode(pdf_bytes).decode()

                    st.markdown(
                        f"""
                        <a href="data:application/pdf;base64,{b64}" target="_blank">
                            📄 Open Consent Term
                        </a>
                        """,
                        unsafe_allow_html=True
                    )

                    st.session_state.consent_term_opened = True

                else:
                    st.error("Consent term file not found.")

        with col_term_b:
            if pdf_exists:
                with open(consent_pdf_path, "rb") as f:
                    st.download_button(
                        "⬇ Download Consent Term",
                        data=f,
                        file_name="Consentimento_Informado_Focus_Group_DOMMx.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )

        consent = st.checkbox(
            "I consent to the use of my personal data for DOMMx *",
            key="chk_register_consent",
            disabled=not st.session_state.consent_term_opened
        )

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
                    consent_pdf_path = os.path.join(
                        BASE_DIR,
                        "data",
                        "general",
                        "Consentimento_Informado_Focus_Group_DOMMx.pdf"
                    )

                    pdf_bytes = None
                    if os.path.isfile(consent_pdf_path):
                        try:
                            with open(consent_pdf_path, "rb") as f:
                                pdf_bytes = f.read()
                        except Exception:
                            pdf_bytes = None

                    # Email: user + admin confirming consent, with attachment
                    if pdf_bytes:
                        attachments = [{
                            "filename": "Consentimento_Informado_Focus_Group_DOMMx.pdf",
                            "content": pdf_bytes,
                            "mime": "application/pdf"
                        }]
                    else:
                        attachments = None

                    try:
                        # user email
                        send_email(
                            payload["email"].strip(),
                            "Consent Given - DOMMx Focus Group",
                            "Your account was created and your consent was registered.\n\nAttached: Consent Term.",
                            attachments=attachments
                        )
                    except Exception:
                        pass

                    if admin_email:
                        try:
                            send_email(
                                admin_email,
                                "Consent Given - DOMMx Focus Group",
                                f"User gave consent: {payload['email']}\n\nAttached: Consent Term.",
                                attachments=attachments
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
                
                try:
                    existing_user = load_user(email.strip())
                except Exception:
                    error_box.error("Temporary connection issue. Please try again.")
                    return

                if existing_user:
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
    
    if "generating_report" not in st.session_state:
        st.session_state.generating_report = False

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

            st.success(st._html_tr("You have already completed all actions for this project."))

            st.markdown(
                """
                <style>

                div[data-testid="stButton"] > button,
                div[data-testid="stDownloadButton"] > button {

                    height: 72px !important;                           
                    border-radius: 10px !important;

                    padding: 18px 24px !important;  /* mais largo */
                    font-size: 10px !important;
                    font-weight: 600 !important;
                    line-height: 1.25 !important;

                    white-space: normal !important; /* permite quebra */
                    word-break: break-word !important;
                    text-align: center !important;
                }

                </style>
                """,
                unsafe_allow_html=True
            )

            # state flags (avoid duplicate ids / rerun safe)
            if "_revoke_consent_pending" not in st.session_state:
                st.session_state._revoke_consent_pending = False
            if "_confirm_revoke_consent" not in st.session_state:
                st.session_state._confirm_revoke_consent = False

            col_r1, col_r2, col_r3 = st.columns(3)

            current_locale = st.session_state.get("locale") or "us"

            repo = get_repository()

            report_service = AIReportService(
                base_dir=BASE_DIR,
                repo=repo
            )
           
            with col_r1:

                if "report_docx_bytes" not in st.session_state:

                    if st.button(
                        st._html_tr("📄 Generate Report"),
                        use_container_width=True,
                        disabled=st.session_state.generating_report
                    ):

                        st.session_state.generating_report = True

                        with st.spinner(st._html_tr("Generating report...")):

                            st.session_state.report_docx_bytes = report_service.generate_report_docx(
                                project_id=selected_project,
                                user_id=st.session_state.get("user_id"),
                                is_admin=st.session_state.get("is_admin", False),
                                language=current_locale,
                                force_regen=False
                            )

                        st.session_state.generating_report = False
                        st.rerun()

                else:

                    docx_bytes = st.session_state.report_docx_bytes

                    st.download_button(
                        label=st._html_tr("📄 Download Report"),
                        data=docx_bytes,
                        file_name="DOMMx_Report.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True,
                        key="btn_download_final_report_finished",
                    )

                    st.success("✔ Report ready. Click the button again to download.")

            with col_r2:
                if st.button(st._html_tr("↩ Log off"), use_container_width=True, key="btn_back_to_login_finished"):
                    # limpa cache do report
                    st.session_state.pop("report_docx_bytes", None)
                    st.session_state.app_mode = "login"
                    st.session_state.pop("_temp_user", None)
                    st.rerun()
                #st.caption("Sair")

            with col_r3:
                if st.button(st._html_tr("🗑 Delete Account"), use_container_width=True, key="btn_revoke_consent_open"):
                    st.session_state._confirm_revoke_consent = True                    
                    st.rerun()
                st.caption(st._tr("Revoke Consent and delete account"))
                    

            if st.session_state.get("_confirm_revoke_consent"):
                st.warning(st._html_tr("This will permanently delete your account and ALL your data. This action cannot be undone."))

                confirm_revoke = st.checkbox(
                    st._html_tr("I understand and I want to permanently delete my account and revoke consent."),
                    key="chk_confirm_revoke_consent_finished",
                    disabled=st.session_state._revoke_consent_pending,
                )

                col_c1, col_c2 = st.columns(2)

                with col_c1:
                    if st.button(
                        st._html_tr("Confirm"),
                        use_container_width=True,
                        key="btn_confirm_revoke_consent_finished",
                        disabled=(not confirm_revoke) or st.session_state._revoke_consent_pending
                    ):
                        st.session_state._revoke_consent_pending = True
                        st.rerun()

                with col_c2:
                    if st.button(
                        st._html_tr("Cancel"),
                        use_container_width=True,
                        key="btn_cancel_revoke_consent_finished",
                        disabled=st.session_state._revoke_consent_pending
                    ):
                        st.session_state._confirm_revoke_consent = False
                        st.rerun()

            # execute delete on rerun (safe)
            if st.session_state.get("_revoke_consent_pending"):
                with st.spinner(st._html_tr("Revoking consent and deleting account...")):
                    try:
                        user_hash = str(st.session_state.get("user_id") or "").strip()

                        # ---------- load user email (source of truth) ----------
                        current_user = load_user_by_hash(user_hash)
                        user_email = (current_user.get("email") if current_user else None) or user.get("email")

                        # ---------- PDF attachment (real BASE_DIR path) ----------
                        consent_pdf_path = os.path.join(
                            BASE_DIR,
                            "data",
                            "general",
                            "Consentimento_Informado_Focus_Group_DOMMx.pdf"
                        )

                        pdf_bytes = None
                        if os.path.isfile(consent_pdf_path):
                            try:
                                with open(consent_pdf_path, "rb") as f:
                                    pdf_bytes = f.read()
                            except Exception:
                                pdf_bytes = None

                        attachments = None
                        if pdf_bytes:
                            attachments = [{
                                "filename": "Consentimento_Informado_Focus_Group_DOMMx.pdf",
                                "content": pdf_bytes,
                                "mime": "application/pdf"
                            }]

                        # ---------- delete data (same logic as account.py) ----------
                        tables_with_user_id = [
                            "results",
                            "usersprojects",
                            "finished_assessments",
                            "logs",
                        ]

                        for table in tables_with_user_id:
                            try:
                                repo.delete(table, {"user_id": user_hash})
                            except Exception:
                                pass

                        try:
                            repo.delete("users", {"email_hash": user_hash})
                        except Exception:
                            pass

                        # ---------- emails ----------
                        admin_email = get_env("SMTP_USER")

                        # email user: consent revoked + attachment
                        if user_email:
                            try:
                                send_email(
                                    user_email,
                                    st._html_tr(
                                    "Consent Revoked - DOMMx Focus Group",
                                    "Your consent was revoked and your account (and all associated data) was deleted.\n\nAttached: Consent Term."),
                                    attachments=attachments
                                )
                            except Exception:
                                pass

                        # email admin: consent revoked + attachment
                        if admin_email:
                            try:
                                send_email(
                                    admin_email,
                                    "Consent Revoked - DOMMx Focus Group",
                                    f"User revoked consent and deleted the account: {user_email or user_hash}\n\nAttached: Consent Term.",
                                    attachments=attachments
                                )
                            except Exception:
                                pass

                        # ---------- logout / clear session ----------
                        for key in list(st.session_state.keys()):
                            del st.session_state[key]

                        st.session_state.app_mode = "login"
                        st.rerun()

                    except Exception as e:
                        st.error(str(e))
                        st.session_state._revoke_consent_pending = False
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
                st.session_state.selected_project_id = selected_project

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
                general_dir = os.path.join(project_root, "general")

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


