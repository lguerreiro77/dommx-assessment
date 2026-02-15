import os
import re
import time

import pycountry
import streamlit as st

from auth.email_service import send_email
from core.config import APP_TITLE
from storage.user_project_storage import get_all_projects, get_projects_for_user
from storage.user_storage import load_user, save_user, verify_password


# =========================================================
# Countries combobox
# =========================================================
def get_countries():
    countries = []
    for country in pycountry.countries:
        code = country.alpha_2
        name = country.name
        flag = "".join(chr(127397 + ord(c)) for c in code)  # emoji flag
        countries.append(f"{flag} {name} ({code})")
    countries.sort()
    return countries


# =========================================================
# ENV SAFE
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
    ADMINS = ADMINS_RAW
else:
    ADMINS = [x.strip() for x in str(ADMINS_RAW).split(",") if x.strip()]


# =========================================================
# FLASH (UI messages that survive rerun)
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
            f"""
            <h3 style='text-align:center; margin-bottom:20px;'>
                {APP_TITLE}
            </h3>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            """
            <h3 style='text-align:center; margin-bottom:15px;'>
                Login
            </h3>
            """,
            unsafe_allow_html=True,
        )

        _flash_render()

        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")

        error_placeholder = st.empty()
        if "login_error" in st.session_state:
            error_placeholder.error(st.session_state.login_error)
            if time.time() - st.session_state.login_error_time > 2:
                st.session_state.pop("login_error", None)
                st.session_state.pop("login_error_time", None)
                st.rerun()

        if st.button("Login", use_container_width=True):
            user = load_user(email)

            if not user or not verify_password(password, user["password_hash"]):
                st.session_state.login_error = "User does not exist or password is incorrect."
                st.session_state.login_error_time = time.time()
                st.rerun()

            st.session_state._temp_user = user
            st.session_state.app_mode = "select_project"
            st.rerun()

        # Create Account (email-first)
        if st.button("Create Account", use_container_width=True):
            if not email or not re.match(r"[^@]+@[^@]+\.[^@]+", email):
                st.session_state.login_error = "Enter a valid email first."
                st.session_state.login_error_time = time.time()
                st.rerun()

            existing = load_user(email)
            if existing:
                st.session_state.login_error = "This email already exists. Please login."
                st.session_state.login_error_time = time.time()
                st.rerun()

            st.session_state.register_prefill_email = email.strip()
            st.session_state.app_mode = "register"
            st.rerun()


# =========================================================
# REGISTER
# =========================================================
def render_register():
    left, center, right = st.columns([1, 4, 1])

    with center:
        st.markdown(
            f"""
            <h3 style='text-align:center; margin-bottom:10px;'>
                {APP_TITLE}
            </h3>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("<h4 style='text-align:center;'>Create Account</h4>", unsafe_allow_html=True)
        st.caption("* Required fields")

        error_box = st.empty()

        prefill_email = st.session_state.get("register_prefill_email", "")

        full_name = st.text_input("Full Name *", key="reg_full_name")
        email = st.text_input("Email *", value=prefill_email, key="reg_email")
        password = st.text_input("Password *", type="password", key="reg_pw")
        confirm_password = st.text_input("Confirm Password *", type="password", key="reg_pw2")

        company = st.text_input("Company", key="reg_company")
        department = st.text_input("Department", key="reg_department")
        job_title = st.text_input("Job Title", key="reg_job_title")
        phone = st.text_input("Phone", key="reg_phone")

        countries = get_countries()
        selected_country = st.selectbox(
            "Country *",
            countries,
            index=None,
            placeholder="Choose your country",
            key="register_country",
        )

        state_province = st.text_input("State/Province", key="reg_state")
        city = st.text_input("City", key="reg_city")

        consent = st.checkbox("I consent to the use of my personal data for DOMMx *", key="reg_consent")

        col_save, col_back = st.columns(2)

        with col_save:
            if st.button("Save", use_container_width=True):
                # VALIDATION (no early return that hides Back)
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

                if email.strip() and load_user(email.strip()):
                    errors.append("User already exists.")

                if errors:
                    error_box.error("\n".join(errors))
                else:
                    created = save_user(
                        email=email.strip(),
                        password=password,
                        full_name=full_name.strip(),
                        company=company.strip(),
                        department=department.strip(),
                        job_title=job_title.strip(),
                        phone=phone.strip(),
                        country=selected_country,
                        state_province=state_province.strip(),
                        city=city.strip(),
                        consent=True,
                    )
                    admin_email = get_env("SMTP_USER")
                    if admin_email:
                        send_email(
                        admin_email,
                        "New User Registration",
                        f"New user created: {email.strip()}"
                    )
                    
                    if not created:
                        error_box.error("User already exists.")
                    else:
                        st.session_state.pop("register_prefill_email", None)
                        _flash_set("User created successfully. Please login.", "success")
                        st.session_state.app_mode = "login"
                        st.rerun()

        with col_back:
            if st.button("Back", use_container_width=True):
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

    # ---- tratar is_active corretamente ----
    active_projects = []
    for p in all_projects:
        raw_active = p.get("is_active", True)

        if isinstance(raw_active, bool):
            active_value = raw_active
        else:
            active_value = str(raw_active).strip().lower() == "true"

        if active_value:
            active_projects.append(p)

    # ---- filtrar associação / open access ----
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
            f"""
            <h3 style='text-align:center; margin-bottom:10px;'>
                {APP_TITLE}
            </h3>
            """,
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
            key="select_project_id",
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

        col_enter, col_request = st.columns(2)

        with col_enter:
            if st.button(
                "Enter",
                use_container_width=True,
                disabled=not (has_access or allow_open),
            ):
                st.session_state.user_id = user_id
                st.session_state.active_project = selected_project
                st.session_state.is_admin = (user.get("email") in ADMINS)
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
                            f"""User: {user.get('email', '')}
Requested Project: {project_map.get(selected_project, selected_project)}
""",
                        )
                    st.session_state.app_mode = "login"
                    st.session_state.pop("_temp_user", None)
                    st.rerun()

