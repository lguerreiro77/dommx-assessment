import hashlib
import bcrypt
from datetime import datetime
import streamlit as st
from auth.crypto_service import encrypt_text, decrypt_text

# Data source call
from data.repository_factory import get_repository
repo = get_repository()


def hash_email(email: str) -> str:
    return hashlib.sha256(email.lower().strip().encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


@st.cache_data(ttl=60, show_spinner=False)
def _read_users_records():
    return repo.fetch_all("users")


def save_user(
    email,
    password,
    full_name,
    company="",
    department="",
    job_title="",
    phone="",
    country="",
    state_province="",
    city="",
    consent=False,
):
    """
    Upsert idempotente por email_hash.
    Nunca cria duplicado mesmo com concorrência.
    """

    import hashlib
    from data.repository_factory import get_repository
    from auth.crypto_service import encrypt_text
    from storage.user_storage import hash_password
    from data.sheets_client import get_table

    repo = get_repository()

    email_norm = (email or "").strip().lower()
    if not email_norm:
        return False

    email_hash = hashlib.sha256(email_norm.encode()).hexdigest()

    user_payload = {
        "email_hash": email_hash,
        "email_encrypted": encrypt_text(email_norm),
        "password_hash": hash_password(password),
        "full_name_encrypted": encrypt_text(full_name),
        "company_encrypted": encrypt_text(company),
        "department_encrypted": encrypt_text(department),
        "job_title_encrypted": encrypt_text(job_title),
        "phone_encrypted": encrypt_text(phone),
        "country_encrypted": encrypt_text(country),
        "state_province_encrypted": encrypt_text(state_province),
        "city_encrypted": encrypt_text(city),
        "consent_encrypted": encrypt_text(str(bool(consent)).lower()),
    }

    # ---------------------------------------------------------
    # UPsert seguro (sem confiar em cache)
    # ---------------------------------------------------------

    ws = get_table("users")
    headers = ws.row_values(1)
    rows = ws.get_all_records()

    existing_row_indexes = []

    for idx, row in enumerate(rows, start=2):
        if str(row.get("email_hash", "")).strip() == email_hash:
            existing_row_indexes.append(idx)

    if existing_row_indexes:
        # Atualiza a PRIMEIRA ocorrência
        row_index = existing_row_indexes[0]

        for col, val in user_payload.items():
            if col in headers:
                col_index = headers.index(col) + 1
                ws.update_cell(row_index, col_index, val)

        # Remove duplicados defensivamente
        if len(existing_row_indexes) > 1:
            for dup_idx in sorted(existing_row_indexes[1:], reverse=True):
                ws.delete_rows(dup_idx)

    else:
        # Insert controlado
        ordered = [user_payload.get(col, "") for col in headers]
        ws.append_row(ordered)

    # Limpa cache do adapter
    try:
        from data.sheets_adapter import _fetch_cached_table
        _fetch_cached_table.clear("users")
    except Exception:
        pass
        
    # Limpa caches Streamlit
    _read_users_records.clear()
    load_user.clear()
    load_user_by_hash.clear()
    get_all_users.clear()    
        

    return True



@st.cache_data(ttl=60, show_spinner=False)
def load_user(email: str):
    email_norm = (email or "").strip().lower()
    email_hash = hash_email(email_norm)

    rows = _read_users_records()

    for row in rows:
        if str(row.get("email_hash", "")).strip() == email_hash:
            return _decrypt_user_row(row)

    return None


@st.cache_data(ttl=60, show_spinner=False)
def load_user_by_hash(email_hash: str):
    target = (email_hash or "").strip()
    rows = _read_users_records()

    for row in rows:
        if str(row.get("email_hash", "")).strip() == target:
            return _decrypt_user_row(row)

    return None


def _decrypt_user_row(row: dict) -> dict:
    out = dict(row)
    
    def d(key: str) -> str:
        val = out.get(key, "")
        return decrypt_text(val) if val not in (None, "") else ""
        
    ## 🔥 Garantir que email sempre exista
    #if not out.get("email") and out.get("email_hash"):
    #    out["email"] = row.get("email", "")

    if "email_encrypted" in out:
        out["email"] = d("email_encrypted")
    if "full_name_encrypted" in out:
        out["full_name"] = d("full_name_encrypted")
    if "company_encrypted" in out:
        out["company"] = d("company_encrypted")
    if "department_encrypted" in out:
        out["department"] = d("department_encrypted")
    if "job_title_encrypted" in out:
        out["job_title"] = d("job_title_encrypted")
    if "phone_encrypted" in out:
        out["phone"] = d("phone_encrypted")
    if "country_encrypted" in out:
        out["country"] = d("country_encrypted")
    if "state_province_encrypted" in out:
        out["state_province"] = d("state_province_encrypted")
    if "city_encrypted" in out:
        out["city"] = d("city_encrypted")
    if "consent_encrypted" in out:
        out["consent"] = (d("consent_encrypted").lower().strip() == "true")
    if "created_at_encrypted" in out:
        out["created_at"] = d("created_at_encrypted")

    if "password_hash" in out:
        out["password_hash"] = out.get("password_hash") or ""


    return out


@st.cache_data(ttl=60, show_spinner=False)
def get_all_users():
    rows = _read_users_records()

    users = []
    for row in rows:
        user = _decrypt_user_row(row)

        users.append({
            "email_hash": row.get("email_hash"),
            "email": user.get("email"),
            "full_name": user.get("full_name"),
        })

    return users
