import json
from datetime import datetime
import streamlit as st
from storage.google_sheets import get_sheet
from auth.crypto_service import encrypt_text, decrypt_text


@st.cache_data(ttl=120, show_spinner=False)
def _results_headers():
    sheet = get_sheet("results")
    headers = sheet.row_values(1)
    return [h.strip() for h in headers if str(h).strip()]


@st.cache_data(ttl=120, show_spinner=False)
def _results_user_index():
    """
    Índice user_id -> número da linha (2..n)
    Lê só a coluna A uma vez por TTL.
    """
    sheet = get_sheet("results")
    col = sheet.col_values(1)  # inclui header
    idx = {}
    for i, v in enumerate(col[1:], start=2):
        key = str(v).strip()
        if key and key not in idx:
            idx[key] = i
    return idx


def _row_to_dict(row_values: list) -> dict:
    headers = _results_headers()
    out = {}
    for i, h in enumerate(headers):
        out[h] = row_values[i] if i < len(row_values) else ""
    return out


def save_results(user_id: str, payload: dict):
    """
    Payload esperado:
    {
      "answers": {...},
      "last_session": {"dom_idx": int, "q_idx": int}
    }
    """
    sheet = get_sheet("results")

    user_id = str(user_id).strip()
    answers_json = json.dumps(payload, ensure_ascii=False)
    enc = encrypt_text(answers_json)

    dom_idx = int(payload.get("last_session", {}).get("dom_idx", 0))
    q_idx = int(payload.get("last_session", {}).get("q_idx", 0))
    ts = datetime.utcnow().isoformat()

    idx = _results_user_index()
    row_num = idx.get(user_id)

    if row_num:
        sheet.update(f"A{row_num}:D{row_num}", [[user_id, enc, dom_idx, q_idx]])
        sheet.update(f"E{row_num}", [[ts]])
    else:
        sheet.append_row([user_id, enc, dom_idx, q_idx, ts])

    # invalida índice após escrita
    _results_user_index.clear()
    return True


@st.cache_data(ttl=60, show_spinner=False)
def load_results(user_id: str):
    sheet = get_sheet("results")
    user_id = str(user_id).strip()

    idx = _results_user_index()
    row_num = idx.get(user_id)
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
