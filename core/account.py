import streamlit as st
import os

from storage.user_storage import get_all_users, load_user_by_hash, hash_password,get_all_users

from storage.google_sheets import get_sheet
from auth.crypto_service import encrypt_text
from auth.email_service import send_email


@st.cache_data(ttl=120)
def _users_index():
    sheet = get_sheet("users")
    col = sheet.col_values(1)
    return {str(v).strip(): i + 2 for i, v in enumerate(col[1:]) if v}


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
    with st.expander("Dados pessoais", expanded=True):

        full_name = st.text_input("Nome completo *", value=user_data.get("full_name") or "")
        company = st.text_input("Empresa", value=user_data.get("company") or "")
        department = st.text_input("Departamento", value=user_data.get("department") or "")
        job_title = st.text_input("Cargo", value=user_data.get("job_title") or "")
        phone = st.text_input("Telefone", value=user_data.get("phone") or "")
        country = st.text_input("País *", value=user_data.get("country") or "")
        state = st.text_input("Estado/Província", value=user_data.get("state_province") or "")
        city = st.text_input("Cidade", value=user_data.get("city") or "")

        if st.button("Update"):

            if not full_name.strip():
                st.error("Full name is required.")
                return

            if not country.strip():
                st.error("Country is required.")
                return

            sheet = get_sheet("users")
            col = sheet.col_values(1)  # email_hash

            row_number = None
            target = str(user_hash).strip()

            for i, value in enumerate(col[1:], start=2):
                if str(value).strip() == target:
                    row_number = i
                    break

            if row_number is None:
                st.error("User not found.")
                return

            sheet.update(
                f"D{row_number}:K{row_number}",
                [[
                    encrypt_text(full_name),
                    encrypt_text(company),
                    encrypt_text(department),
                    encrypt_text(job_title),
                    encrypt_text(phone),
                    encrypt_text(country),
                    encrypt_text(state),
                    encrypt_text(city),
                ]]
            )

            load_user_by_hash.clear()
            
            try:
                get_all_users.clear()
            except:
                pass
                
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

        idx = _users_index().get(user_hash)
        if not idx:
            st.error("User index not found.")
            return

        sheet = get_sheet("users")
        sheet.update(f"C{idx}", [[hash_password(new_password)]])

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

            # Envio de email
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

            # Se o usuário deletou a própria conta → logout
            if str(session_state.get("user_id")).strip() == str(user_hash).strip():

                for key in list(st.session_state.keys()):
                    del st.session_state[key]

                st.session_state.app_mode = "login"
                st.rerun()

            # Se foi admin deletando outro usuário → NÃO deslogar
            else:
                st.session_state.account_deleted = True
                st.session_state.confirm_delete = False
                st.rerun()

def _delete_account(user_hash):

    user_hash = str(user_hash).strip()

    users = get_sheet("users")
    results = get_sheet("results")
    up = get_sheet("usersprojects")

    for sheet, col in [(users, "email_hash"), (results, "user_id"), (up, "user_id")]:
        rows = sheet.get_all_records()
        for i in reversed(range(len(rows))):
            if str(rows[i].get(col, "")).strip() == user_hash:
                sheet.delete_rows(i + 2)
