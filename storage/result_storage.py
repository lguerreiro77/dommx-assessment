import json
from datetime import datetime
import streamlit as st
from storage.google_sheets import get_sheet
from auth.crypto_service import encrypt_text, decrypt_text


# =========================================================
# HEADERS
# =========================================================
@st.cache_data(ttl=120, show_spinner=False)
def _results_headers():
    sheet = get_sheet("results")
    headers = sheet.row_values(1)
    return [h.strip() for h in headers if str(h).strip()]


# =========================================================
# INDEX (user_id + project_id)
# =========================================================
@st.cache_data(ttl=120, show_spinner=False)
def _results_index():
    """
    Índice (user_id, project_id) -> número da linha (2..n)
    """
    sheet = get_sheet("results")
    rows = sheet.get_all_records()

    idx = {}

    for i, row in enumerate(rows, start=2):
        uid = str(row.get("user_id", "")).strip()
        pid = str(row.get("project_id", "")).strip()

        if uid and pid:
            key = (uid, pid)
            if key not in idx:
                idx[key] = i

    return idx


def _row_to_dict(row_values: list) -> dict:
    headers = _results_headers()
    out = {}
    for i, h in enumerate(headers):
        out[h] = row_values[i] if i < len(row_values) else ""
    return out


# =========================================================
# SAVE
# =========================================================
def save_results(user_id: str, project_id: str, answers_dict: dict):

    sheet = get_sheet("results")

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

    idx = _results_index()
    row_num = idx.get((user_id, project_id))

    if row_num:
        sheet.update(
            f"A{row_num}:C{row_num}",
            [[user_id, project_id, enc]]
        )
        sheet.update(f"F{row_num}", [[ts]])
    else:
        sheet.append_row([
            user_id,
            project_id,
            enc,
            "",  # dom_idx inutilizado
            "",  # q_idx inutilizado
            ts
        ])

    _results_index.clear()
    
    return True




# =========================================================
# LOAD
# =========================================================
@st.cache_data(ttl=60, show_spinner=False)
def load_results(user_id: str, project_id: str):

    sheet = get_sheet("results")

    user_id = str(user_id).strip()
    project_id = str(project_id).strip()

    idx = _results_index()
    row_num = idx.get((user_id, project_id))

    if not row_num:
        return None

    row_values = sheet.row_values(row_num)
    row = _row_to_dict(row_values)

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

