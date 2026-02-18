import json
from datetime import datetime
import streamlit as st

from data.repository_factory import get_repository
from auth.crypto_service import encrypt_text, decrypt_text

repo = get_repository()


# =========================================================
# SAVE
# =========================================================
def save_results(user_id: str, project_id: str, answers_dict: dict):

    user_id = str(user_id).strip()
    project_id = str(project_id).strip()
    ts = datetime.utcnow().isoformat()

    payload = {
        "version": 2,
        "meta": {
            "completed": False,
            "last_update": ts
        },
        "answers": answers_dict or {}
    }

    answers_json = json.dumps(payload, ensure_ascii=False)
    enc = encrypt_text(answers_json)

    rows = repo.fetch_all("results")

    exists = any(
        str(r.get("user_id", "")).strip() == user_id and
        str(r.get("project_id", "")).strip() == project_id
        for r in rows
    )

    if exists:
        repo.update(
            "results",
            {"user_id": user_id, "project_id": project_id},
            {
                "answers_json_encrypted": enc,
                "updated_at": ts
            }
        )
    else:
        repo.insert(
            "results",
            {
                "user_id": user_id,
                "project_id": project_id,
                "answers_json_encrypted": enc,
                "updated_at": ts
            }
        )

    return True


# =========================================================
# LOAD
# =========================================================
@st.cache_data(ttl=60, show_spinner=False, show_spinner=False)
def load_results(user_id: str, project_id: str):

    user_id = str(user_id).strip()
    project_id = str(project_id).strip()

    rows = repo.fetch_all("results")

    for row in rows:
        if (
            str(row.get("user_id", "")).strip() == user_id
            and str(row.get("project_id", "")).strip() == project_id
        ):

            enc = row.get("answers_json_encrypted") or ""
            if not enc:
                return None

            try:
                data = json.loads(decrypt_text(enc))
            except Exception:
                return None

            if not isinstance(data, dict):
                return None

            return {
                "answers": data.get("answers", {}),
                "meta": data.get("meta", {}),
                "completed": data.get("meta", {}).get("completed", False)
            }

    return None
