import io
import json
import os
import yaml
import pandas as pd
import streamlit as st

from core.config import BASE_DIR, resolve_path, get_project_root
from data.repository_factory import get_repository
from auth.crypto_service import decrypt_text

   
repo = get_repository()


def _safe_load_yaml(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def _format_datetime(ts):

    if not ts:
        return ""

    try:
        from datetime import datetime
        dt = datetime.fromisoformat(str(ts))
        return dt.strftime("%d/%m/%Y %H:%M:%S")
    except Exception:
        return str(ts)
        

def export_all_to_excel():

        
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
    comments = repo.fetch_all("comments") or []

    if not results and not comments:
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
            
        try:
            country = decrypt_text(u.get("country_encrypted"))
        except Exception:
            country = ""
            
        # limpar formato "🇪🇸 Spain (ES)" → "Spain"
        if country:
            try:
                if "(" in country:
                    country = country.split("(")[0]
                country = country[2:].strip()
            except Exception:
                country = country.strip()
                
        
        user_lookup[email_hash] = {
            "full_name": full_name,
            "email": email,
            "country": country
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

    flow_path = resolve_path(BASE_DIR, f"data/{config.get('main_flow', 'flow.yaml')}")
    orch_path = resolve_path(BASE_DIR, f"data/{config.get('main_orchestration', 'default_execution.yaml')}")

    flow = safe_load(flow_path) or {}
    orch = safe_load(orch_path) or {}    
   
    req_list = orch.get("execution_request", []) or []
    domain_flow = flow.get("Domain_flow", []) or []     
            
    
    lang = str(st.session_state.get("locale") or "us").strip().lower()
        
    project_root = get_project_root()

    if not project_root or not os.path.isdir(project_root):
        project_root = os.path.join(BASE_DIR, "data")
    
    domains_dir = ""

    if project_root:
        domains_dir = os.path.join(project_root, "domains")

    if not domains_dir or not os.path.isdir(domains_dir):
        domains_dir = os.path.join(BASE_DIR, "data", "domains")
    
    # -----------------------------
    # COMMENTS LOOKUP
    # -----------------------------
    import xml.etree.ElementTree as ET

    from collections import defaultdict
    comment_lookup = defaultdict(list)

    for c in comments:

        xml_raw = c.get("comment")

        try:
            root = ET.fromstring(xml_raw)

            domain = str(root.findtext("Domain") or "").strip()
                          
            question = str(root.findtext("Question") or "").strip().upper()
            text = str(root.findtext("Text") or "").strip()

            key = (
                str(c.get("user_id")).strip(),
                str(c.get("project_id")).strip(),
                domain,
                question
            )

            comment_lookup[key].append({
                "text": text,
                "timestamp": c.get("created_at")
            })

        except Exception:
            continue

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

        if decision_tree and domains_dir:

            tree_path = os.path.join(
                domains_dir,
                lang,
                decision_tree
            )

            # fallback simples caso o locale não exista
            if not os.path.isfile(tree_path):
                tree_path = os.path.join(
                    domains_dir,
                    "us",
                    decision_tree
                )

            tree_data = safe_load(tree_path) or {}
            question_block = tree_data.get("questions") or {}

            if not isinstance(question_block, dict):
                question_block = {}

            for qid, q_content in question_block.items():
                if not isinstance(q_content, dict):
                    continue

                qid_norm = str(qid).strip().upper()
                qtext = (
                    q_content.get("question")
                    or q_content.get("text")
                    or ""
                ).strip()

                qtext_map[qid_norm] = qtext

        domain_maps[f"domain_{idx}"] = {
            "acronym": acronym,
            "name": name,
            "qtext": qtext_map
        }
    
    # -----------------------------
    # DOMAIN ID MAP (para comments)
    # -----------------------------
    domain_id_map = {}

    for key, meta in domain_maps.items():
        try:
            idx = key.split("_")[1]
            domain_id_map[idx] = meta
        except:
            pass
                        
            
    # -----------------------------
    # BUILD ROWS
    # -----------------------------
    rows = []

    for r in results:

        user_id = r.get("user_id")
        project_id = r.get("project_id")        
                   
        last_update_ts = r.get("last_update_timestamp", "")        
              

        # ✅ Apenas projetos existentes
        if project_id not in valid_project_ids:
            continue

        full_name = user_lookup.get(user_id, {}).get("full_name", "")
        email = user_lookup.get(user_id, {}).get("email", "")
        country = user_lookup.get(user_id, {}).get("country", "")
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

            try:
                domain_order = int(domain_key.split("_")[1])
            except:
                domain_order = 999
                
            dom_meta = domain_maps.get(domain_key)
            dom_id = domain_key.split("_")[1]

            if not dom_meta:
                try:
                    idx = int(domain_key.split("_")[1])
                    dom_meta = domain_maps.get(f"domain_{idx}", {})
                except:
                    dom_meta = {}                       

            domain_acr = dom_meta.get("acronym") or domain_key
            domain_name = dom_meta.get("name") or ""
            qtext_map = dom_meta.get("qtext") or {}            

            for qid, score in qmap.items():

                qid_str = str(qid).strip()
                qid_norm = qid_str.upper()
                qtext = qtext_map.get(qid_norm, "")
                maturity_label = LIKERT.get(score, "")   

                # -----------------------------
                # COMMENT LOOKUP
                # -----------------------------
                comment_list = comment_lookup.get(
                    (
                        str(user_id).strip(),
                        str(project_id).strip(),
                        str(dom_id).strip(),
                        qid_norm
                    ),
                    []
                )                
                
                comment_text = ""
                comment_ts = ""

                if comment_list:
                    comment_text = " | ".join(c["text"] for c in comment_list if c.get("text"))

                    timestamps = [c["timestamp"] for c in comment_list if c.get("timestamp")]
                    comment_ts = max(timestamps) if timestamps else ""
                                    
                # -----------------------------
                # LAST UPDATE = max(result, comment)
                # -----------------------------
                final_update_ts = last_update_ts

                if comment_ts:
                    try:
                        from datetime import datetime

                        result_dt = datetime.fromisoformat(last_update_ts) if last_update_ts else None
                        comment_dt = datetime.fromisoformat(comment_ts)

                        if not result_dt or comment_dt > result_dt:
                            final_update_ts = comment_ts

                    except Exception:
                        pass

                # converter para display                

                final_update_display = _format_datetime(final_update_ts)
                
                # -----------------------------
                
                rows.append({
                    "_user_id": user_id,
                    "_project_id": project_id,
                    "Full Name": full_name,
                    "Email": email,
                    "Country": country,
                    "Project": project_name,
                    "Domain Order": domain_order,   
                    "Domain": domain_acr,
                    "Domain Name": domain_name,
                    "Question ID": qid_str,
                    "Question": qtext,
                    "Answer (Score)": score,
                    "Maturity Level": maturity_label,
                    "Comment Text": comment_text,
                    "Last Update": final_update_display
                })

    # -----------------------------------
    # ADD COMMENTS WITHOUT ANSWERS
    # -----------------------------------

    existing_keys = {
        (
            str(r.get("_user_id","")).strip(),
            str(r.get("_project_id","")).strip(),
            str(r.get("Question ID","")).strip().upper()
        )
        for r in rows
    }

    for key, clist in comment_lookup.items():

        user_id, project_id, dom_id, qid = key

        if project_id not in valid_project_ids:
            continue

        user_info = user_lookup.get(user_id, {})
        full_name = user_info.get("full_name", "")
        email = user_info.get("email", "")
        country = user_info.get("country", "")

        project_name = project_lookup.get(project_id, "")
        
        dom_meta = domain_id_map.get(str(int(dom_id) - 1), {})

        try:
            domain_order = int(dom_id)
        except:
            domain_order = 999

        domain_acr = dom_meta.get("acronym") or f"D{dom_id}"
        domain_name = dom_meta.get("name") or ""

        qtext_map = dom_meta.get("qtext") or {}
        qtext = qtext_map.get(str(qid).upper(), "")

        check_key = (
            email.strip(),
            project_name.strip(),
            domain_acr.strip(),
            qid.strip().upper()
        )

        if check_key in existing_keys:
            continue

        for cdata in clist:

            rows.append({
                "_user_id": user_id,
                "_project_id": project_id,
                "Full Name": full_name,
                "Email": email,
                "Country": country,
                "Project": project_name,
                "Domain Order": domain_order,
                "Domain": domain_acr,
                "Domain Name": domain_name,
                "Question ID": qid,
                "Question": qtext,
                "Answer (Score)": "NA",
                "Maturity Level": "NA",
                "Comment Text": cdata.get("text", ""),
                "Last Update": _format_datetime(cdata.get("timestamp"))
            })
            
    if not rows:
       return b""
    
    for r in rows:
        r.pop("_user_id", None)
        r.pop("_project_id", None)
        
    df = pd.DataFrame(rows)
    
    df["Answer (Score)"] = df["Answer (Score)"].replace("", "NA")
    df["Answer (Score)"] = df["Answer (Score)"].astype(str)

    # ordenação elegante
    df = df.sort_values(
        by=["Project", "Full Name", "Domain Order", "Question ID"],
        kind="stable"
    )

    output = io.BytesIO()
    df.to_excel(output, index=False)

    return output.getvalue()
