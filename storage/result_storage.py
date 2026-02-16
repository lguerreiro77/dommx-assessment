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
def save_results(user_id: str, payload: dict):

    sheet = get_sheet("results")

    user_id = str(user_id).strip()
    project_id = str(st.session_state.get("active_project", "")).strip()

    answers_json = json.dumps(payload, ensure_ascii=False)
    enc = encrypt_text(answers_json)

    dom_idx = int(payload.get("last_session", {}).get("dom_idx", 0))
    q_idx = int(payload.get("last_session", {}).get("q_idx", 0))
    ts = datetime.utcnow().isoformat()

    idx = _results_index()
    row_num = idx.get((user_id, project_id))

    if row_num:
        sheet.update(
            f"A{row_num}:E{row_num}",
            [[user_id, project_id, enc, dom_idx, q_idx]]
        )
        sheet.update(f"F{row_num}", [[ts]])
    else:
        sheet.append_row([
            user_id,
            project_id,
            enc,
            dom_idx,
            q_idx,
            ts
        ])

    _results_index.clear()
    return True


# =========================================================
# LOAD
# =========================================================
@st.cache_data(ttl=60, show_spinner=False)
def load_results(user_id: str):

    sheet = get_sheet("results")

    user_id = str(user_id).strip()
    project_id = str(st.session_state.get("active_project", "")).strip()

    idx = _results_index()
    row_num = idx.get((user_id, project_id))

    if not row_num:
        return None

    row_values = sheet.row_values(row_num)
    row = _row_to_dict(row_values)

    enc = row.get("answers_json_encrypted") or row.get("answers_json") or ""
    if not enc:
        return None

    data = json.loads(decrypt_text(enc))

    answers = data.get("answers", {}) if isinstance(data, dict) else {}
    last_session = data.get("last_session", {}) if isinstance(data, dict) else {}

    return {
        "answers": answers,
        "dom_idx": int(last_session.get("dom_idx", 0)),
        "q_idx": int(last_session.get("q_idx", 0)),
    }
