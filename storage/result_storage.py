import json
from datetime import datetime
from storage.google_sheets import get_sheet
from auth.crypto_service import encrypt_text, decrypt_text


def save_results(user_id: str, payload: dict):
    """
    Payload esperado:
    {
      "answers": {...},
      "last_session": {"dom_idx": int, "q_idx": int}
    }
    """
    sheet = get_sheet("results")
    rows = sheet.get_all_records()

    answers_json = json.dumps(payload, ensure_ascii=False)
    enc = encrypt_text(answers_json)

    dom_idx = int(payload.get("last_session", {}).get("dom_idx", 0))
    q_idx = int(payload.get("last_session", {}).get("q_idx", 0))
    ts = datetime.utcnow().isoformat()

    # upsert 1 linha por user_id
    for i, r in enumerate(rows, start=2):  # start=2 por causa do header
        if str(r.get("user_id", "")).strip() == str(user_id).strip():
            sheet.update(f"A{i}:D{i}", [[user_id, enc, dom_idx, q_idx]])
            sheet.update(f"E{i}", [[ts]])
            return True

    sheet.append_row([user_id, enc, dom_idx, q_idx, ts])
    return True


def load_results(user_id: str):
    sheet = get_sheet("results")
    rows = sheet.get_all_records()

    for r in rows:
        if str(r.get("user_id", "")).strip() == str(user_id).strip():
            enc = r.get("answers_json_encrypted") or r.get("answers_json") or ""
            if not enc:
                return None

            data = json.loads(decrypt_text(enc))

            # Normaliza retorno para o renderer
            answers = data.get("answers", {}) if isinstance(data, dict) else {}
            last_session = data.get("last_session", {}) if isinstance(data, dict) else {}

            return {
                "answers": answers,
                "dom_idx": int(last_session.get("dom_idx", 0)),
                "q_idx": int(last_session.get("q_idx", 0)),
            }

    return None
