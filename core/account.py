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
    
    is_admin = bool(session_state.get("is_admin"))

    users = get_all_users()

    if is_admin:
        emails = [u.get("email") or "" for u in users]
        emails = [e for e in emails if e]
        
        selected_email = st.selectbox("Select user", emails, disabled=not is_admin)
        
        selected = next(
            (u for u in users if u.get("email") == selected_email),
            None
        )

        if not selected:
            st.warning("Selected user not found.")
            return
        
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

    if "_account_update_pending" not in st.session_state:
        st.session_state._account_update_pending = False
    if "_account_update_payload" not in st.session_state:
        st.session_state._account_update_payload = None

    if "_pwd_update_pending" not in st.session_state:
        st.session_state._pwd_update_pending = False
    if "_pwd_update_payload" not in st.session_state:
        st.session_state._pwd_update_payload = None

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

        if st.session_state._account_update_pending and st.session_state._account_update_payload:
            with st.spinner("Updating..."):
                try:
                    payload = st.session_state._account_update_payload

                    repo.update(
                        "users",
                        {"email_hash": user_hash},
                        {
                            "full_name_encrypted": encrypt_text(payload["full_name"]),
                            "company_encrypted": encrypt_text(payload["company"]),
                            "department_encrypted": encrypt_text(payload["department"]),
                            "job_title_encrypted": encrypt_text(payload["job_title"]),
                            "phone_encrypted": encrypt_text(payload["phone"]),
                            "country_encrypted": encrypt_text(payload["country"]),
                            "state_province_encrypted": encrypt_text(payload["state"]),
                            "city_encrypted": encrypt_text(payload["city"]),
                        }
                    )

                    _read_users_records.clear()
                    load_user_by_hash.clear()
                    get_all_users.clear()

                    updated_user = load_user_by_hash(user_hash)
                    st.session_state.user = updated_user

                    st.session_state.account_updated = True

                except Exception as e:
                    st.error(str(e))

                finally:
                    st.session_state._account_update_pending = False
                    st.session_state._account_update_payload = None
                    st.rerun()

        if st.button("Update", disabled=st.session_state._account_update_pending):

            if not full_name.strip():
                st.error("Full name is required.")
                return

            if not country.strip():
                st.error("Country is required.")
                return

            st.session_state._account_update_pending = True
            st.session_state._account_update_payload = {
                "full_name": full_name,
                "company": company,
                "department": department,
                "job_title": job_title,
                "phone": phone,
                "country": country,
                "state": state,
                "city": city,
            }
            st.rerun()

    st.divider()

    # ========================
    # PASSWORD
    # ========================
    st.subheader("Change Password")

    new_password = st.text_input("New password", type="password")
    confirm_password = st.text_input("Confirm password", type="password")

    if st.session_state._pwd_update_pending and st.session_state._pwd_update_payload:
        with st.spinner("Updating password..."):
            try:
                payload = st.session_state._pwd_update_payload

                repo.update(
                    "users",
                    {"email_hash": user_hash},
                    {"password_hash": hash_password(payload["new_password"])}
                )

                _read_users_records.clear()
                load_user_by_hash.clear()
                get_all_users.clear()

                st.success("Password updated successfully.")

            except Exception as e:
                st.error(str(e))

            finally:
                st.session_state._pwd_update_pending = False
                st.session_state._pwd_update_payload = None
                st.rerun()

    if st.button("Update Password", disabled=st.session_state._pwd_update_pending):

        if new_password != confirm_password:
            st.error("Passwords do not match.")
            return

        st.session_state._pwd_update_pending = True
        st.session_state._pwd_update_payload = {
            "new_password": new_password
        }
        st.rerun()

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

    # Tabelas que possuem user_id
    tables_with_user_id = [
        "results",
        "usersprojects",
        "finished_assessments",
        "logs",
    ]

    # Delete em todas as tabelas dependentes
    for table in tables_with_user_id:
        try:
            repo.delete(table, {"user_id": user_hash})
        except Exception:
            pass

    # Delete do próprio user (usa email_hash como chave)
    repo.delete("users", {"email_hash": user_hash})

    # Limpa caches
    _read_users_records.clear()
    load_user_by_hash.clear()
    get_all_users.clear()
