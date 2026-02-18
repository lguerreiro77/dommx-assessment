import io
import os
import json
import yaml
import pandas as pd

from core.config import BASE_DIR
from data.repository_factory import get_repository
from auth.crypto_service import decrypt_text

repo = get_repository()

FILESYSTEM_SETUP_PATH = os.path.join(BASE_DIR, "filesystem_setup.yaml")


def _ci_pick_child(dir_path: str, target_name: str) -> str:
    if not os.path.isdir(dir_path):
        return os.path.join(dir_path, target_name)
    for name in os.listdir(dir_path):
        if name.lower() == target_name.lower():
            return os.path.join(dir_path, name)
    return os.path.join(dir_path, target_name)


def _load_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _load_context():
    fs = _load_yaml(FILESYSTEM_SETUP_PATH)
    flow_path = os.path.join(BASE_DIR, fs["orchestrator_config"]["main_flow"])
    orch_path = os.path.join(BASE_DIR, fs["orchestrator_config"]["main_orchestration"])

    flow = _load_yaml(flow_path)
    orch = _load_yaml(orch_path)

    lang = orch.get("language", "Default")

    domains_root = os.path.join(BASE_DIR, "data", "domains")
    language_root = _ci_pick_child(domains_root, "Language")
    lang_folder = _ci_pick_child(language_root, lang)

    domain_names = {}
    domain_questions = {}

    for d in flow.get("Domain_flow", []):
        domain_id = d.get("domain_id")
        domain_name = d.get("name", "")
        decision_file = d.get("files", {}).get("decision_tree", "")

        if not domain_id or not decision_file:
            continue

        domain_names[str(domain_id)] = domain_name

        tree_path = _ci_pick_child(lang_folder, decision_file)
        tree = _load_yaml(tree_path)
        domain_questions[str(domain_id)] = tree.get("questions", {}) or {}

    for dom_id in list(domain_questions.keys()):
        q = domain_questions[dom_id]
        domain_questions[dom_id] = {str(k).lower(): v for k, v in q.items()}

    return domain_names, domain_questions


def export_all_to_excel():
    domain_names, domain_questions = _load_context()

    rows = repo.fetch_all("results")

    export_rows = []

    for r in rows:
        user_id = r.get("user_id", "")
        enc = r.get("answers_json_encrypted") or ""
        if not enc:
            continue

        from core.flow_engine import add_message

        try:
            decrypted = decrypt_text(enc)
            payload = json.loads(decrypted)
        except Exception:
            add_message("Warning: Invalid encrypted payload found during export.", "warning")
            continue

        answers = payload.get("answers", {}) if isinstance(payload, dict) else {}

        for domain_id, questions in answers.items():

            if not isinstance(questions, dict):
                continue

            for q_id, score in questions.items():

                q_key = str(q_id).lower()

                domain_name = domain_names.get(str(domain_id), "")
                found_q = domain_questions.get(str(domain_id), {}).get(q_key)

                question_text = found_q.get("text", "") if found_q else ""

                MATURITY_LABELS = {
                    0: "Initial",
                    1: "Ad-hoc",
                    2: "Developing",
                    3: "Defined",
                    4: "Managed",
                    5: "Optimized"
                }

                label = MATURITY_LABELS.get(int(score), "")

                export_rows.append({
                    "Id_User": user_id,
                    "Domain": domain_name,
                    "Question": f"{q_id}: {question_text}" if question_text else str(q_id),
                    "Answer": score,
                    "Result": label
                })

    df = pd.DataFrame(export_rows, columns=["Id_User", "Domain", "Question", "Answer", "Result"])

    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)

    return output
