import json
import re
import yaml
from pathlib import Path
from typing import Dict, Any

from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib

from dotenv import load_dotenv
import os

load_dotenv()

from openai import OpenAI


# =========================================================
# BASE DIR
# =========================================================

BASE_DIR = Path(__file__).resolve().parent.parent

# =========================================================
# IA para extrair subject do recomendacoes e notas
# =========================================================

from openai import OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def generate_theory_phrase(text: str) -> str:
    if not text:
        print("⚠ Empty text sent to GPT")
        return None

    try:
        print("→ Sending to GPT:", text[:80])

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Extract the theoretical foundation phrase from the text. "
                        "Return only the framework name plus the immediate conceptual scope."
                    ),
                },
                {"role": "user", "content": text},
            ],
        )

        result = response.choices[0].message.content.strip()
        print("← GPT returned:", result)
        return result

    except Exception as e:
        print("🔥 GPT ERROR:", e)
        return None


# =========================================================
# LOAD YAML
# =========================================================

def load_yaml(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# =========================================================
# NORMALIZATION + CLASSIFICATION
# =========================================================

def normalize_reference(ref: str) -> str:
    s = (ref or "").strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\b(chapter|chap\.?|cap[ií]tulo|cap\.?)\b", "ch", s, flags=re.IGNORECASE)
    s = re.sub(r"\b(section|sec\.?)\b", "sec", s, flags=re.IGNORECASE)
    s = re.sub(r"\b(dmbok 2|dmbok2|dmbok)\b", "dmbok2", s, flags=re.IGNORECASE)
    return s.strip(" .;,")


def classify_reference(norm: str) -> str:
    s = norm.lower()

    if "dama" in s or "dmbok2" in s:
        return "DAMA_DMBOK2"
    if "dcam" in s:
        return "DCAM"
    if "cmmi" in s:
        return "CMMI"
    if "gdpr" in s:
        return "GDPR"
    if "iso" in s:
        return "ISO"
    if "nist" in s:
        return "NIST"
    if "cobit" in s:
        return "COBIT"
    if "mesh" in s:
        return "DATA_MESH"
    if "dommx" in s or "zenodo" in s or "slr" in s:
        return "SLR_DOMMx"

    return "OTHER"


def extract_tail(text: str):
    if not text:
        return None
    m = re.search(r"\(([^()]*)\)\s*$", str(text).strip())
    return m.group(1).strip() if m else None


# =========================================================
# EXTRACTION CORE
# =========================================================

def extract_with_context(domain_code: str, dt_path: Path, ac_path: Path):

    dt = load_yaml(dt_path)
    ac = load_yaml(ac_path)

    registry = {}

    def register(ref, domain=None, question_id=None, action_code=None, source=None, field=None):

        if not ref:
            return

        original = str(ref).strip()
        normalized = normalize_reference(original)
        category = classify_reference(normalized)

        if normalized not in registry:
            registry[normalized] = {
                "original": original,
                "normalized": normalized,
                "category": category,
                "contexts": []
            }

        registry[normalized]["contexts"].append({
            "source": source,
            "field": field,
            "IDs": {
                "domain": domain,
                "question_id": question_id,
                "action_code": action_code
            }
        })

    # ----------------------------
    # DECISION TREE - recursive
    # ----------------------------

    def walk(obj, question_id=None):
        if isinstance(obj, dict):
            for k, v in obj.items():

                if str(k).lower() in ("cross_reference", "cross_references", "references"):
                    if isinstance(v, list):
                        for x in v:
                            register(
                                x,
                                domain=domain_code,
                                question_id=question_id,
                                action_code=None,
                                source="decision_tree",
                                field=k
                            )
                    else:
                        register(
                            v,
                            domain=domain_code,
                            question_id=question_id,
                            action_code=None,
                            source="decision_tree",
                            field=k
                        )

                if k == "questions" and isinstance(v, dict):
                    for qid, qdata in v.items():
                        walk(qdata, question_id=qid)
                else:
                    walk(v, question_id)

        elif isinstance(obj, list):
            for x in obj:
                walk(x, question_id)

    walk(dt)

    ## ----------------------------
    # ACTION CATALOG - FULL WALK
    # ----------------------------

    def walk_action_catalog(action_code, obj):

        if isinstance(obj, dict):
            for k, v in obj.items():

                # Campo references explícito
                if str(k).lower() == "references":
                    if isinstance(v, list):
                        for x in v:
                            register(
                                x,
                                domain=domain_code,
                                question_id=None,
                                action_code=action_code,
                                source="action_catalog",
                                field="references"
                            )
                    else:
                        register(
                            v,
                            domain=domain_code,
                            question_id=None,
                            action_code=action_code,
                            source="action_catalog",
                            field="references"
                        )

                # Referência no final de texto (recommendations, notes, etc.)
                if isinstance(v, str):
                    tail = extract_tail(v)
                    if tail:
                        register(
                            tail,
                            domain=domain_code,
                            question_id=None,
                            action_code=action_code,
                            source="action_catalog",
                            field=f"{k}_tail"
                        )

                walk_action_catalog(action_code, v)

        elif isinstance(obj, list):
            for x in obj:
                walk_action_catalog(action_code, x)


    # Executar para cada action
    if "action_catalog" in ac:
        ac_root = ac["action_catalog"]
    else:
        ac_root = ac

    for action_code, action in ac_root.items():
        if isinstance(action, dict):
            walk_action_catalog(action_code, action)

    return registry


# =========================================================
# FLOW LOADER
# =========================================================

def load_domains_from_flow():

    flow_path = BASE_DIR / "data" / "general" / "flow.yaml"

    flow = load_yaml(flow_path)

    domains = []

    for item in flow.get("Domain_flow", []):
        domains.append({
            "acronym": item.get("acronym"),
            "decision_tree": item["files"].get("decision_tree"),
            "action_catalog": item["files"].get("action_catalog")
        })

    return domains


# =========================================================
# SAVE
# =========================================================

def save_global_theory_index(data):

    output_dir = BASE_DIR / "data" / "global" / "theory"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / "citations_with_context.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return output_path


gpt_cache = {}

def cached_generate(text):

    if not text:
        return None

    key = hashlib.md5(text.encode()).hexdigest()

    if key in gpt_cache:
        return gpt_cache[key]

    # Reduz drasticamente tokens
    short_text = text[:600]

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": "Return only: <Framework> + short concept. Max 12 words."
            },
            {"role": "user", "content": short_text}
        ],
    )

    result = response.choices[0].message.content.strip()

    gpt_cache[key] = result
    return result

# =========================================================
# MAIN Function
# =========================================================


def build_theory_structure(domain_code, dt_path, ac_path):

    dt = load_yaml(dt_path)
    ac = load_yaml(ac_path)

    ac_root = ac.get("action_catalog", ac)
    
    action_cache = {
        k.strip(): v
        for k, v in ac_root.items()
    }

    result = {
        "questions": {}
    }

    questions = dt.get("decision_tree", {}).get("questions", {}) \
        if "decision_tree" in dt else dt.get("questions", {})

    # --------------------------------------------------
    # 1️⃣ COLETAR TODOS OS TEXTOS DISTINCT
    # --------------------------------------------------

    distinct_texts = set()

    for qdata in questions.values():
        for score_map in qdata.get("score_action_mapping", {}).values():

            action_code = score_map.get("action_code")
            if not action_code:
                continue

            action_data = action_cache.get(action_code.strip(), {})

            def find_nested(obj, key):
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        if k == key:
                            return v
                        r = find_nested(v, key)
                        if r is not None:
                            return r
                elif isinstance(obj, list):
                    for x in obj:
                        r = find_nested(x, key)
                        if r is not None:
                            return r
                return None

            procedures = find_nested(action_data, "procedures") or []

            for p in procedures:
                rec = find_nested(p, "recommendations")
                notes = find_nested(p, "notes")

                if isinstance(rec, list):
                    rec = " ".join(rec)
                if isinstance(notes, list):
                    notes = " ".join(notes)

                if rec:
                    distinct_texts.add(rec.strip())
                if notes:
                    distinct_texts.add(notes.strip())

    print(f"Total DISTINCT theory texts: {len(distinct_texts)}")

    # --------------------------------------------------
    # 2️⃣ PARALELISMO GPT
    # --------------------------------------------------

    subject_map = {}

    max_workers = min(8, os.cpu_count() or 4)

    total = len(distinct_texts)
    completed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:

        futures = {
            executor.submit(cached_generate, text): text
            for text in distinct_texts
        }

        for future in as_completed(futures):
            original = futures[future]
            subject = future.result()
            subject_map[original] = subject

            completed += 1
            percent = int((completed / total) * 100)
            print(f"Progress: {completed}/{total} ({percent}%)", end="\r")

    # --------------------------------------------------
    # 3️⃣ CONSTRUIR ESTRUTURA FINAL
    # --------------------------------------------------

    for qid, qdata in questions.items():

        question_block = {
            "score_action_mapping": {}
        }

        score_map = qdata.get("score_action_mapping", {})
        cross_refs = qdata.get("cross_reference") or []

        if not isinstance(cross_refs, list):
            cross_refs = [cross_refs]

        for score, mapping in score_map.items():

            action_code = mapping.get("action_code")
            if not action_code:
                continue

            action_data = ac_root.get(action_code.strip(), {})

            def find_nested(obj, key):
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        if k == key:
                            return v
                        r = find_nested(v, key)
                        if r is not None:
                            return r
                elif isinstance(obj, list):
                    for x in obj:
                        r = find_nested(x, key)
                        if r is not None:
                            return r
                return None

            procedures = find_nested(action_data, "procedures") or []

            procedures_block = {}

            for p in procedures:
                p_number = p.get("number")
                if p_number is None:
                    continue

                rec = find_nested(p, "recommendations")
                notes = find_nested(p, "notes")

                if isinstance(rec, list):
                    rec = " ".join(rec)
                if isinstance(notes, list):
                    notes = " ".join(notes)

                rec_subject = subject_map.get(rec)
                notes_subject = subject_map.get(notes)

                def build_key(subject):
                    if not subject:
                        return None
                    normalized = normalize_reference(subject)
                    framework = classify_reference(normalized)
                    return f"{framework}|{normalized}"

                procedures_block[str(p_number)] = {
                    "theory": {
                        "recommendations_subject": rec_subject,
                        "recommendations_theory_key": build_key(rec_subject),
                        "notes_subject": notes_subject,
                        "notes_theory_key": build_key(notes_subject)
                    }
                }

            # ----------------------------
            # Build Cross Reference Block
            # ----------------------------

            cross_block = []

            for ref in cross_refs:
                if not ref:
                    continue

                normalized = normalize_reference(ref)
                framework = classify_reference(normalized)

                cross_block.append({
                    "reference": ref,
                    "theory_key": f"{framework}|{normalized}"
                })

            # ----------------------------
            # Final score mapping block
            # ----------------------------

            question_block["score_action_mapping"][str(score)] = {
                "action_code": action_code,
                "theory": {
                    "decision_tree_cross_reference": cross_block
                },
                "procedures": procedures_block
            }

        result["questions"][str(qid)] = question_block

    return result

# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":

    language = "us"
    domains = load_domains_from_flow()

    print("Domains detected:", [d["acronym"] for d in domains])

    theory_index = {}

    for d in domains:

        dt_path = BASE_DIR / "data" / "domains" / language / d["decision_tree"]
        ac_path = BASE_DIR / "data" / "domains" / language / d["action_catalog"]

        print(f"\nProcessing {d['acronym']}")
        print("DT exists:", dt_path.exists())
        print("AC exists:", ac_path.exists())

        if not dt_path.exists() or not ac_path.exists():
            print("Skipping...")
            continue

        # IMPORTANTE: usar build_theory_structure
        domain_theory = build_theory_structure(
            d["acronym"],            
            dt_path,
            ac_path
        )

        theory_index[d["acronym"]] = domain_theory

    # salvar
    output_dir = BASE_DIR / "data" / "global" / "theory"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / "theory_index.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(theory_index, f, indent=2, ensure_ascii=False)

    print(f"\nSaved to: {output_path}")