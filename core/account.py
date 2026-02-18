import streamlit as st
import os

from storage.user_storage import (
    get_all_users,
    load_user_by_hash,
    hash_password,
    _read_users_records  # 🔥 necessário para limpar cache raiz
)

from data.repository_factory import get_repository
from auth.crypto_service import encrypt_text
from auth.email_service import send_email

repo = get_repository()


def _get_env(name: str):
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return os.getenv(name)


def _get_admin_email():
    try:
        return st.secrets.get("ADMIN_EMAIL")
    except Exception:
        return None


def render_account_page(session_state):

    st.title("User / Account")

    if st.session_state.get("account_updated"):
        st.success("Record updated successfully.")
        del st.session_state["account_updated"]

    if st.session_state.get("account_deleted"):
        st.success("Account deleted successfully.")
        del st.session_state["account_deleted"]

    is_admin = str(session_state.get("is_admin", "")).lower() == "true"

    users = get_all_users()

    if is_admin:
        emails = [u["email"] for u in users if u.get("email")]
        selected_email = st.selectbox("Select user", emails)
        selected = next(u for u in users if u["email"] == selected_email)
        user_hash = str(selected["email_hash"]).strip()
    else:
        user_hash = str(session_state.get("user_id")).strip()

    user_data = load_user_by_hash(user_hash)
    if not user_data:
        st.error("User not found.")
        return

    st.write(f"**Email:** {user_data.get('email')}")
    st.write(f"**Consent:** {user_data.get('consent')}")

    st.caption(
        "Consent can't be changed. If required you must delete the whole account and recreate it."
    )

    st.divider()

    # ========================
    # PERSONAL DATA
    # ========================
    with st.expander("Personal Data", expanded=True):

        full_name = st.text_input("Full Name *", value=user_data.get("full_name") or "")
        company = st.text_input("Company", value=user_data.get("company") or "")
        department = st.text_input("Department", value=user_data.get("department") or "")
        job_title = st.text_input("Job Title", value=user_data.get("job_title") or "")
        phone = st.text_input("Phone", value=user_data.get("phone") or "")
        country = st.text_input("Country *", value=user_data.get("country") or "")
        state = st.text_input("State", value=user_data.get("state_province") or "")
        city = st.text_input("City", value=user_data.get("city") or "")

        if st.button("Update"):

            if not full_name.strip():
                st.error("Full name is required.")
                return

            if not country.strip():
                st.error("Country is required.")
                return

            repo.update(
                "users",
                {"email_hash": user_hash},
                {
                    "full_name_encrypted": encrypt_text(full_name),
                    "company_encrypted": encrypt_text(company),
                    "department_encrypted": encrypt_text(department),
                    "job_title_encrypted": encrypt_text(job_title),
                    "phone_encrypted": encrypt_text(phone),
                    "country_encrypted": encrypt_text(country),
                    "state_province_encrypted": encrypt_text(state),
                    "city_encrypted": encrypt_text(city),
                }
            )

            # 🔥 LIMPA TODOS OS CACHES
            _read_users_records.clear()
            load_user_by_hash.clear()
            get_all_users.clear()

            # 🔥 RECARREGA DADOS ATUALIZADOS
            updated_user = load_user_by_hash(user_hash)
            st.session_state.user = updated_user

            st.session_state.account_updated = True
            st.rerun()

    st.divider()

    # ========================
    # PASSWORD
    # ========================
    st.subheader("Change Password")

    new_password = st.text_input("New password", type="password")
    confirm_password = st.text_input("Confirm password", type="password")

    if st.button("Update Password"):

        if new_password != confirm_password:
            st.error("Passwords do not match.")
            return

        repo.update(
            "users",
            {"email_hash": user_hash},
            {"password_hash": hash_password(new_password)}
        )

        _read_users_records.clear()
        load_user_by_hash.clear()
        get_all_users.clear()

        st.success("Password updated successfully.")

    st.divider()

    # ========================
    # DELETE ACCOUNT
    # ========================
    st.subheader("Delete Account")
    st.warning("This will permanently delete ALL your data.")

    if st.button("Delete account"):
        st.session_state.confirm_delete = True

    if st.session_state.get("confirm_delete"):
        confirm = st.checkbox("I confirm permanent deletion.")

        if st.button("Confirm delete", disabled=not confirm):

            _delete_account(user_hash)

            admin_email = _get_env("SMTP_USER")
            if admin_email:
                try:
                    send_email(
                        admin_email,
                        "Account Deleted",
                        f"User deleted the account: {user_data.get('email')}"
                    )
                except Exception:
                    pass

            if str(session_state.get("user_id")).strip() == user_hash:

                for key in list(st.session_state.keys()):
                    del st.session_state[key]

                st.session_state.app_mode = "login"
                st.rerun()
            else:
                st.session_state.account_deleted = True
                st.session_state.confirm_delete = False
                st.rerun()


def _delete_account(user_hash):

    user_hash = str(user_hash).strip()

    repo.delete("users", {"email_hash": user_hash})
    repo.delete("results", {"user_id": user_hash})
    repo.delete("usersprojects", {"user_id": user_hash})

    _read_users_records.clear()
    load_user_by_hash.clear()
    get_all_users.clear()
