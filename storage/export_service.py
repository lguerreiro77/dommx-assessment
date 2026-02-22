import io
import json
import yaml
import pandas as pd

from core.config import BASE_DIR, resolve_path
from data.repository_factory import get_repository
from auth.crypto_service import decrypt_text

repo = get_repository()


def _safe_load_yaml(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def _build_domain_maps():
    """
    Mapeia domain_{idx} -> metadata do domínio (acronym, name, question_text_map)
    usando:
      - filesystem_setup.yaml -> flow.yaml + orchestration yaml
      - flow.yaml -> arquivos por domínio
      - orchestration -> execution_request + language
      - decision_tree por domínio -> texto das perguntas
    """
    fs_path = resolve_path(BASE_DIR, "FileSystem_Setup.yaml")
    fs_setup = _safe_load_yaml(fs_path) or {}
    orch_cfg = (fs_setup.get("orchestrator_config") or {})

    flow_path = resolve_path(BASE_DIR, orch_cfg.get("main_flow", "flow.yaml"))
    orch_path = resolve_path(BASE_DIR, orch_cfg.get("main_orchestration", "default_execution.yaml"))

    flow = _safe_load_yaml(flow_path) or {}
    orch = _safe_load_yaml(orch_path) or {}

    req_list = orch.get("execution_request", []) or []
    domain_flow = flow.get("Domain_flow", []) or []

    lang_raw = orch.get("language", "Default")
    lang = str(lang_raw or "Default").strip() or "Default"
    if lang.lower() == "default":
        lang = "Default"

    # domain_{idx} -> (acronym, name, decision_tree_path)
    idx_to_meta = {}

    for idx, req in enumerate(req_list):
        dom_id = req.get("domain")
        dom_meta = next((d for d in domain_flow if str(d.get("domain_id")) == str(dom_id)), None) or {}

        acronym = (dom_meta.get("acronym") or str(dom_id) or f"domain_{idx}").strip()
        name = (dom_meta.get("name") or "").strip()

        files = dom_meta.get("files") or {}
        decision_tree = files.get("decision_tree")

        if decision_tree:
            tree_path = resolve_path(BASE_DIR, f"data/domains/Language/{lang}/{decision_tree}")
        else:
            tree_path = None

        idx_to_meta[f"domain_{idx}"] = {
            "acronym": acronym,
            "name": name,
            "tree_path": tree_path,
            "qtext": {}
        }

    # carregar textos das perguntas por domínio
    for dkey, meta in idx_to_meta.items():
        tree_path = meta.get("tree_path")
        if not tree_path:
            continue

        tree_data = _safe_load_yaml(tree_path) or {}
        questions = tree_data.get("questions", {}) or {}

        # normaliza chaves para comparar (Q1, q1 etc.)
        qtext = {}
        for qid, qinfo in questions.items():
            qid_str = str(qid).strip()
            text = (qinfo.get("question") or qinfo.get("text") or "").strip()
            qtext[qid_str.lower()] = text

        meta["qtext"] = qtext

    return idx_to_meta


def export_all_to_excel():

    import io
    import json
    import yaml
    import pandas as pd

    from core.config import BASE_DIR, resolve_path
    from auth.crypto_service import decrypt_text

    # -----------------------------
    # LIKERT MAP
    # -----------------------------
    LIKERT = {
        0: "Initial",
        1: "Ad-hoc",
        2: "Emerging",
        3: "Defined",
        4: "Managed",
        5: "Optimized",
    }

    users = repo.fetch_all("users") or []
    projects = repo.fetch_all("projects") or []
    results = repo.fetch_all("results") or []

    if not results:
        return b""

    # -----------------------------
    # USERS LOOKUP
    # -----------------------------
    user_lookup = {}

    for u in users:
        email_hash = (u.get("email_hash") or "").strip()
        if not email_hash:
            continue

        try:
            full_name = decrypt_text(u.get("full_name_encrypted"))
        except Exception:
            full_name = ""

        try:
            email = decrypt_text(u.get("email_encrypted"))
        except Exception:
            email = ""

        user_lookup[email_hash] = {
            "full_name": full_name,
            "email": email
        }

    # -----------------------------
    # PROJECT LOOKUP
    # -----------------------------
    project_lookup = {
        p.get("project_id"): p.get("name")
        for p in projects
    }

    valid_project_ids = set(project_lookup.keys())

    # -----------------------------
    # LOAD FLOW + ORCHESTRATION
    # -----------------------------
    def safe_load(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except Exception:
            return None

    fs_path = resolve_path(BASE_DIR, "FileSystem_Setup.yaml")
    fs_setup = safe_load(fs_path) or {}
    config = (fs_setup.get("orchestrator_config") or {})

    flow_path = resolve_path(BASE_DIR, config.get("main_flow", "flow.yaml"))
    orch_path = resolve_path(BASE_DIR, config.get("main_orchestration", "default_execution.yaml"))

    flow = safe_load(flow_path) or {}
    orch = safe_load(orch_path) or {}

    req_list = orch.get("execution_request", []) or []
    domain_flow = flow.get("Domain_flow", []) or []

    lang_raw = orch.get("language", "Default")
    lang = str(lang_raw or "Default").strip() or "Default"
    if lang.lower() == "default":
        lang = "Default"

    # -----------------------------
    # DOMAIN MAP (domain_0 → metadata)
    # -----------------------------
    domain_maps = {}

    for idx, req in enumerate(req_list):
        dom_id = req.get("domain")

        dom_meta = next(
            (d for d in domain_flow if str(d.get("domain_id")) == str(dom_id)),
            None
        ) or {}

        acronym = (dom_meta.get("acronym") or f"domain_{idx}").strip()
        name = (dom_meta.get("name") or "").strip()

        decision_tree = (dom_meta.get("files") or {}).get("decision_tree")

        qtext_map = {}

        if decision_tree:
            tree_path = resolve_path(
                BASE_DIR,
                f"data/domains/Language/{lang}/{decision_tree}"
            )

            tree_data = safe_load(tree_path) or {}
            questions = tree_data.get("questions", {}) or {}

            for qid, qinfo in questions.items():
                qid_str = str(qid).strip().lower()
                qtext = (
                    qinfo.get("question")
                    or qinfo.get("text")
                    or ""
                ).strip()

                qtext_map[qid_str] = qtext

        domain_maps[f"domain_{idx}"] = {
            "acronym": acronym,
            "name": name,
            "qtext": qtext_map
        }

    # -----------------------------
    # BUILD ROWS
    # -----------------------------
    rows = []

    for r in results:

        user_id = r.get("user_id")
        project_id = r.get("project_id")
                
        last_update_ts = r.get("last_update_timestamp", "")
        last_update_display = ""

        if last_update_ts:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(last_update_ts)
                last_update_display = dt.strftime("%d/%m/%Y %H:%M:%S")
            except Exception:
                last_update_display = last_update_ts
        

        # ✅ Apenas projetos existentes
        if project_id not in valid_project_ids:
            continue

        full_name = user_lookup.get(user_id, {}).get("full_name", "")
        email = user_lookup.get(user_id, {}).get("email", "")
        project_name = project_lookup.get(project_id, "")
               

        enc = r.get("answers_json_encrypted")
        if not enc:
            continue

        try:
            decrypted = decrypt_text(enc)
            payload = json.loads(decrypted)
        except Exception:
            continue

        # suporta dois formatos
        answers = payload.get("answers") if isinstance(payload, dict) else None
        if answers is None and isinstance(payload, dict):
            answers = payload

        if not isinstance(answers, dict):
            continue

        for domain_key, qmap in answers.items():

            if not isinstance(qmap, dict):
                continue

            dom_meta = domain_maps.get(domain_key, {})
            domain_acr = dom_meta.get("acronym") or domain_key
            domain_name = dom_meta.get("name") or ""
            qtext_map = dom_meta.get("qtext") or {}

            for qid, score in qmap.items():

                qid_str = str(qid).strip()
                qtext = qtext_map.get(qid_str.lower(), "")
                maturity_label = LIKERT.get(score, "")

                rows.append({
                    "Full Name": full_name,
                    "Email": email,
                    "Project": project_name,
                    "Domain": domain_acr,
                    "Domain Name": domain_name,
                    "Question ID": qid_str,
                    "Question": qtext,
                    "Answer (Score)": score,
                    "Maturity Level": maturity_label,
                    "Last Update": last_update_display
                })

    if not rows:
        return b""

    df = pd.DataFrame(rows)

    # ordenação elegante
    df = df.sort_values(
        by=["Project", "Full Name", "Domain", "Question ID"]
    )

    output = io.BytesIO()
    df.to_excel(output, index=False)

    return output.getvalue()
