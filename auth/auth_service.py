import streamlit as st
import re
import yaml
import os
from storage.user_storage import save_user, load_user, hash_text
from storage.result_storage import load_results
from auth.email_service import send_email
from core.config import BASE_DIR, resolve_path
from dotenv import load_dotenv

load_dotenv()

def is_admin(email: str):
    admins = os.getenv("ADMINS", "")
    admin_list = [a.strip().lower() for a in admins.split(",") if a.strip()]
    return email.lower() in admin_list

def load_app_config():
    config_path = resolve_path(BASE_DIR, "app_config.yaml")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except:
        return {}
        
        
def validate_password(password: str):
    if len(password) < 8:
        return "Minimum 8 characters"
    if not re.search(r"[A-Z]", password):
        return "Must contain uppercase letter"
    if not re.search(r"[a-z]", password):
        return "Must contain lowercase letter"
    if not re.search(r"[0-9]", password):
        return "Must contain number"
    if not re.search(r"[!@#$%^&*()_+=\-{}\[\]:;\"'<>,.?/]", password):
        return "Must contain symbol"
    return None


def require_login():

    if st.session_state.get("user_id"):
        return

    # ------------------------------
    # CENTRALIZED LOGIN STYLE
    # ------------------------------

    st.markdown("""
        <style>
        .block-container {
            max-width: 420px;
            margin: auto;
            padding-top: 40px;
        }

        /* Centraliza todos os headers */
        h1, h2, h3 {
            text-align: center !important;
        }

        /* Primeiro título menor */
        h1 {
            font-size: 26px !important;
            font-weight: 600 !important;
            margin-bottom: 5px !important;
        }

        /* Subtítulos */
        h2 {
            font-size: 20px !important;
            margin-top: 10px !important;
        }

        h3 {
            font-size: 18px !important;
        }
        </style>
        """, unsafe_allow_html=True)



    app_config = load_app_config()
    #app_title = app_config.get("title", "DOMMx")

    #st.markdown(
    #    f"<div class='login-title'>{app_title}</div>",
    #    unsafe_allow_html=True
    #)

    st.markdown("### User Access")

    mode = st.radio("", ["Login", "Create account"], horizontal=True)

    email = st.text_input("Email *")
    password = st.text_input("Password *", type="password")

    if mode == "Create account":
        email_confirm = st.text_input("Confirm Email *")
        password_confirm = st.text_input("Confirm Password *", type="password")
        consent = st.checkbox("I accept data protection terms *")

    if st.button("Continue", use_container_width=True):

        if not email or not password:
            st.error("Email and password required")
            st.stop()

        user_id = hash_text(email.lower())

        # -------------------------------------------------
        # CREATE ACCOUNT
        # -------------------------------------------------
        if mode == "Create account":

            if email != email_confirm:
                st.error("Emails do not match")
                st.stop()

            if password != password_confirm:
                st.error("Passwords do not match")
                st.stop()

            error = validate_password(password)
            if error:
                st.error(error)
                st.stop()

            if not consent:
                st.error("You must accept data protection terms")
                st.stop()

            existing_user = load_user(user_id)
            if existing_user:
                st.error("User already registered.")
                st.stop()

            save_user(user_id, {
                "email": email.lower(),
                "password_hash": hash_text(password),
                "consent": True
            })

            try:
                send_email(
                    email,
                    "Account Created",
                    "Your DOMMx account has been successfully created."
                )
            except:
                st.warning("Account created but confirmation email could not be sent.")

            st.success("Account successfully created.")

            st.session_state.user_id = user_id
            
            st.session_state.user_email = email.lower()
            st.session_state.is_admin = is_admin(email.lower())


        # -------------------------------------------------
        # LOGIN
        # -------------------------------------------------
        else:            
            user = load_user(user_id)

            if not user or user["password_hash"] != hash_text(password):
                st.error("Invalid credentials")
                st.stop()

            st.session_state.user_id = user_id
            st.session_state.user_email = user.get("email")
            st.session_state.is_admin = is_admin(user.get("email"))

        # -------------------------------------------------
        # LOAD LAST SESSION
        # -------------------------------------------------

        saved = load_results(user_id)

        if saved:
            st.session_state.answers = saved.get("answers", {})
            st.session_state.last_saved_snapshot = dict(st.session_state.answers)
            st.session_state.dom_idx = saved.get("last_session", {}).get("dom_idx", 0)
            st.session_state.q_idx = saved.get("last_session", {}).get("q_idx", 0)
        else:
            st.session_state.answers = {}
            st.session_state.last_saved_snapshot = {}
            st.session_state.dom_idx = 0
            st.session_state.q_idx = 0

        st.session_state.intro_seen = False

        st.rerun()

    st.stop()
