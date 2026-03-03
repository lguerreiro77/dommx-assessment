# =========================================================
# tree_action_improver.py
#
# DOMMx — Domain Bundle Builder
# Generates FINAL consolidated JSON per domain from:
#   - utils/theory-cluster/tree_output/original/{DOMAIN}_tree_action_cluster.json
#   - utils/theory-cluster/output/{DOMAIN}_theory_cluster_output.json (action catalog)
#   - utils/theory-cluster/_cache/pdf_pages_cache.json (theory text snippets)
#
# Output:
#   - utils/theory-cluster/tree_output/improved/{DOMAIN}_domain_bundle.json
#
# Reuses:
#   - paths
#   - OpenAI connection
#   - simple file-based cache
#   - parallelism
#   - batch processing
#
# =========================================================

import argparse
import hashlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from openai import OpenAI


# =========================================================
# BASE DIRS (keep your existing structure)
# =========================================================

BASE_DIR = Path(__file__).resolve().parent.parent.parent
THEORY_DIR = BASE_DIR / "utils" / "theory-cluster"

TREE_ORIGINAL_DIR = THEORY_DIR / "tree_output" / "original"
TREE_IMPROVED_DIR = THEORY_DIR / "tree_output" / "improved"

THEORY_OUTPUT_DIR = THEORY_DIR / "output"

CACHE_DIR = THEORY_DIR / "_cache"
PDF_CACHE_PATH = CACHE_DIR / "pdf_pages_cache.json"

DOMAIN_CONTEXT_CACHE_PATH = CACHE_DIR / "domain_context_cache.json"
PROCEDURE_MASTER_CACHE_PATH = CACHE_DIR / "procedure_master_cache.json"
PROCEDURE_CASE_CACHE_PATH = CACHE_DIR / "procedure_case_cache.json"


# =========================================================
# DEFAULT CONFIG
# =========================================================

DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_MAX_WORKERS = 4
DEFAULT_ITEMS_PER_CALL = 6  # Prompt 1/2 are long. Keep small.
MAX_RETRY = 3
MAX_CONTEXT_CHARS = 6000


# =========================================================
# OPENAI CLIENT (singleton)
# =========================================================

load_dotenv(BASE_DIR / ".env")
_OPENAI_CLIENT = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# =========================================================
# UTIL (IO)
# =========================================================

def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)


def load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, obj):
    ensure_dir(path.parent)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def safe_read_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return load_json(path)
    except Exception as e:
        print(f"[ERROR] Failed to read JSON: {path} -> {e}")
        return None


# =========================================================
# SIMPLE FILE CACHES
# =========================================================

def _load_cache(path: Path) -> Dict[str, Any]:
    if path.exists():
        try:
            data = load_json(path)
            if isinstance(data, dict):
                return data
        except Exception as e:
            print(f"[WARN] Cache load failed: {path} -> {e}")
    return {}


def _save_cache(path: Path, data: Dict[str, Any]):
    save_json(path, data)


def sha256_str(s: str) -> str:
    return hashlib.sha256((s or "").encode("utf-8")).hexdigest()


def stable_json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


# =========================================================
# PDF THEORY CONTEXT (cached once; per-action slices only)
# =========================================================

def extract_aliases(cross_reference: str) -> List[str]:
    if not cross_reference:
        return []
    clean = cross_reference.replace("(", "").replace(")", "")
    return [i.strip() for i in clean.split(";") if i.strip()]


def build_pdf_lookup(pdf_cache: dict) -> Dict[str, str]:
    """
    pdf_cache expected shape: { page_key: {alias: "...", text: "..."} , ... }
    """
    lookup: Dict[str, str] = {}
    if not isinstance(pdf_cache, dict):
        return lookup

    for item in pdf_cache.values():
        if not isinstance(item, dict):
            continue
        alias = item.get("alias")
        text = item.get("text")
        if alias and text:
            lookup[str(alias)] = str(text)
    return lookup


def resolve_theory_context(cross_reference: str, pdf_lookup: Dict[str, str]) -> str:
    aliases = extract_aliases(cross_reference or "")
    contexts: List[str] = []

    for alias in aliases:
        t = pdf_lookup.get(alias)
        if t:
            contexts.append(t)
        else:
            print(f"[WARN] Alias not in PDF cache: {alias}")

    joined = "\n\n".join(contexts)
    if len(joined) <= MAX_CONTEXT_CHARS:
        return joined
    return joined[:MAX_CONTEXT_CHARS]


# =========================================================
# GPT JSON HELPERS (robust JSON array)
# =========================================================

def try_parse_json_array(text: str) -> Optional[list]:
    if not text:
        return None
    t = text.strip()

    if t.startswith("```"):
        t = t.replace("```json", "").replace("```", "").strip()

    start = t.find("[")
    end = t.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return None

    candidate = t[start:end + 1].strip()
    try:
        obj = json.loads(candidate)
        return obj if isinstance(obj, list) else None
    except Exception:
        return None


def gpt_chat(model: str, messages: List[Dict[str, str]], temperature: float = 0.2) -> str:
    resp = _OPENAI_CLIENT.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature
    )
    return (resp.choices[0].message.content or "").strip()


def call_gpt_json_array(
    model: str,
    prompt: str,
    label: str,
    repair_hint: str = "Return ONLY valid JSON array. No markdown. No commentary."
) -> Optional[list]:
    print(f"\n[GPT] {label}")
    last_raw = None

    for attempt in range(MAX_RETRY):
        try:
            raw = gpt_chat(model, [{"role": "user", "content": prompt}], temperature=0.2)
            last_raw = raw
            parsed = try_parse_json_array(raw)
            if parsed is not None:
                return parsed

            repair_prompt = (
                f"{repair_hint}\n\n"
                f"RAW OUTPUT TO REPAIR:\n{raw}\n\n"
                f"Return the repaired JSON array only."
            )
            repaired = gpt_chat(model, [{"role": "user", "content": repair_prompt}], temperature=0.0)
            parsed2 = try_parse_json_array(repaired)
            if parsed2 is not None:
                return parsed2

            print("⚠ invalid JSON array (attempt failed).")

        except Exception as e:
            print(f"[GPT ERROR] Attempt {attempt + 1}: {e}")
            if attempt == MAX_RETRY - 1:
                raise
            time.sleep(2)

    if last_raw:
        print("[FAIL] Could not parse JSON after retries. Last raw (truncated):")
        print(last_raw[:500])
    return None


def chunk_list(lst: List[Any], n: int):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


# =========================================================
# PROMPT 1 & 2 (your baselines)
# =========================================================

def build_prompt_1(
    theory_context: str,
    domain: str,
    action_code: str,
    action_definition: str,
    maturity_level: Any,
    procedure_title: str,
    recommendations_and_notes: List[str],
    procedure_n: int
) -> str:
    recs = "\n".join([f"- {x}" for x in recommendations_and_notes if x and str(x).strip()])
    if not recs:
        recs = "- (none provided)"

    return f"""
ROLE
You are a senior Data Governance specialist and audit-methodology writer with deep knowledge of DAMA-DMBOK2, DCAM, CMMI, IDGC, and GDPR.

OBJECTIVE
Generate a single procedure description for a maturity model action that consolidates theoretical recommendations into an integrated procedural statement and includes operational metadata.

INPUT
- Domain: {domain}
- Internal Action Code: {action_code}
- Action definition: {action_definition}
- Maturity level: {maturity_level}
- Procedure title: {procedure_title}
- List of theoretical recommendations and notes:
{recs}

INSTRUCTIONS
1. Produce exactly 4 short paragraphs.
2. Use formal audit tone suitable for maturity model documentation.
3. Integrate theory directly into procedural statements (do not cite or explain separately).
4. Preserve all concepts from:
   - DAMA (principles, decision domains, federated scope, responsibility model, stewardship)
   - DCAM (capability scoping and control coverage validation)
   - CMMI (prioritization logic based on maturity gaps, dependency, and risk exposure)
   - IDGC (integrated governance coordination, cross-domain alignment, and control harmonization)
   - GDPR (accountability, purpose limitation, data minimization, protection-by-design, and role responsibility)
5. Do not invent frameworks or terminology.
6. Avoid redundancy and generic wording.
7. Include operational metadata fields before the paragraphs.
8. Estimated implementation time must reflect realistic DAMA/DCAM early-stage governance rollout guidance.

AUTHORITATIVE THEORY CONTEXT (do not contradict; do not invent):
{theory_context}

OUTPUT FORMAT (exactly):
Procedure {procedure_n} — <Title>
Prerequisites: <Prerequisites>
outputs expected: <outputs>
Expected time to implement: <DAMA/DCAM time>

<Paragraph 1>
<Paragraph 2>
<Paragraph 3>
<Paragraph 4>
""".strip()


def build_prompt_2(
    domain: str,
    action_code: str,
    action_definition: str,
    maturity_level: Any,
    procedure_title: str,
    procedure_master_text: str
) -> str:
    return f"""
ROLE
You are a senior Data Governance practitioner translating maturity model procedures into realistic organizational scenarios.

OBJECTIVE
Based on a provided Procedure description, generate a concise simulated real-world case illustrating how an organization would implement the procedure in practice.

INPUT
- Domain: {domain}
- Action code: {action_code}
- Action definition: {action_definition}
- Maturity level: {maturity_level}
- Procedure title: {procedure_title}
- Procedure text (audit-ready):
{procedure_master_text}

INSTRUCTIONS
1. Do not rewrite the procedure.
2. Create a realistic organizational scenario demonstrating implementation.
3. Use concrete but generic enterprise context (e.g., global bank, pharma company, telecom).
4. Show actions taken, actors involved, artifacts produced, and decisions made.
5. Reflect concepts embedded in the procedure including:
   - Governance principles
   - Federated scope
   - Responsibility model
   - Stewardship
   - Capability coverage
   - Risk/maturity prioritization
   - Regulatory and integrated governance alignment
6. Use narrative professional tone (not audit tone).
7. Produce 3–5 short paragraphs.
8. Ensure the case clarifies practical meaning for end users performing assessment or implementation.

OUTPUT FORMAT (exactly):
Simulated case — <Procedure title>

<Paragraph 1 — context>
<Paragraph 2 — governance structuring>
<Paragraph 3 — responsibility and stewardship operationalization>
<Paragraph 4 — capability validation and prioritization outcome>
""".strip()


# =========================================================
# DOMAIN "CONTEXTO" (summary of objectives of all questions)
# =========================================================

def build_domain_context_prompt(domain_name: str, objectives: List[str]) -> str:
    obj_lines = "\n".join([f"- {o.strip()}" for o in objectives if o and str(o).strip()])
    if not obj_lines:
        obj_lines = "- (no objectives provided)"

    return f"""
Você é um redator sênior de documentação de auditoria e maturidade.

Tarefa:
Escreva um único texto de "contexto" em português que consolide o objetivo combinado de todas as questões do domínio "{domain_name}".

Regras:
- Produza 2 a 4 parágrafos curtos, texto corrido.
- Não listar questões.
- Não inventar conceitos não implícitos pelos objetivos.
- Tom neutro, claro, adequado para maturidade/avaliação.
- Saída apenas com os parágrafos, sem título.

Objetivos para consolidar:
{obj_lines}
""".strip()


# =========================================================
# INPUT LOADERS (your real shape)
# =========================================================

def find_domain_files(domain_id: str) -> Tuple[Path, Optional[Path]]:
    tree_path = TREE_ORIGINAL_DIR / f"{domain_id}_tree_action_cluster.json"
    action_path = THEORY_OUTPUT_DIR / f"{domain_id}_theory_cluster_output.json"
    return tree_path, (action_path if action_path.exists() else None)


def extract_domain_metadata(tree: dict, fallback_domain_id: str) -> Dict[str, Any]:
    """
    Your shape:
      "domain": { "acronym": "DG", ... }
    """
    meta = tree.get("domain") if isinstance(tree, dict) else None
    if isinstance(meta, dict):
        acronym = meta.get("acronym") or meta.get("domain_id") or fallback_domain_id
        name = meta.get("name") or meta.get("domain_name") or acronym
        desc = meta.get("description") or ""
        return {"acronym": acronym, "name": name, "description": desc}
    return {"acronym": fallback_domain_id, "name": fallback_domain_id, "description": ""}


def extract_questions(tree: dict) -> List[dict]:
    """
    Your questions list key can be arbitrary (e.g., "cccc").
    We find the first list of dicts that looks like questions: has "question_id".
    """
    if not isinstance(tree, dict):
        return []

    # explicit common guesses first (cheap)
    for k in ["questions", "question_list", "items", "cccc"]:
        v = tree.get(k)
        if isinstance(v, list) and v and isinstance(v[0], dict) and ("question_id" in v[0]):
            return [x for x in v if isinstance(x, dict)]

    # generic scan
    for k, v in tree.items():
        if k == "domain":
            continue
        if isinstance(v, list) and v and isinstance(v[0], dict) and ("question_id" in v[0]):
            return [x for x in v if isinstance(x, dict)]

    return []


def extract_scores_from_question(q: dict) -> List[dict]:
    scores = q.get("scores")
    if isinstance(scores, list):
        return [s for s in scores if isinstance(s, dict)]
    return []


def normalize_score_value(score_obj: dict) -> Optional[Any]:
    # your key: "score"
    if "score" in score_obj:
        return score_obj.get("score")
    # fallback
    for k in ["level", "maturity_level", "value"]:
        if k in score_obj:
            return score_obj.get(k)
    return None


def normalize_action_code_from_score(score_obj: dict) -> Optional[str]:
    # your key: "action_code" (sometimes "Action_Code")
    return score_obj.get("action_code") or score_obj.get("Action_Code") or score_obj.get("Action_Code".lower())


def build_actions_by_score(questions: List[dict]) -> Tuple[List[Any], Dict[str, List[str]], List[str]]:
    score_to_actions: Dict[str, List[str]] = {}
    all_scores: List[Any] = []
    referenced: List[str] = []

    for q in questions:
        for s in extract_scores_from_question(q):
            sv = normalize_score_value(s)
            if sv is None:
                continue

            skey = str(sv)
            if skey not in score_to_actions:
                score_to_actions[skey] = []

            ac = normalize_action_code_from_score(s)
            if ac:
                if ac not in score_to_actions[skey]:
                    score_to_actions[skey].append(ac)
                if ac not in referenced:
                    referenced.append(ac)

            if sv not in all_scores:
                all_scores.append(sv)

    # sort
    def _num(x):
        try:
            return float(x)
        except Exception:
            return None

    numeric = all(_num(x) is not None for x in all_scores) and len(all_scores) > 0
    scores_possible = sorted(all_scores, key=lambda z: float(z)) if numeric else sorted(all_scores, key=lambda z: str(z))

    return scores_possible, score_to_actions, referenced


def extract_objectives(questions: List[dict]) -> List[str]:
    out: List[str] = []
    for q in questions:
        obj = q.get("objective")
        if obj and str(obj).strip():
            out.append(str(obj).strip())
    return out


# =========================================================
# ACTION CATALOG PARSER (your real shape: dict keyed by action code)
# =========================================================

def load_action_catalog(action_path: Path) -> Dict[str, dict]:
    """
    Your shape:
      { "action_catalog": { "DG-01": {...}, "DG-02": {...} } }
    """
    data = safe_read_json(action_path)
    if not data or not isinstance(data, dict):
        return {}

    ac = data.get("action_catalog")
    if isinstance(ac, dict):
        # keys are action_code already
        return {str(k): v for k, v in ac.items() if isinstance(v, dict)}

    # fallback: sometimes already top-level dict of actions
    # (only accept if keys look like codes)
    by_code: Dict[str, dict] = {}
    for k, v in data.items():
        if isinstance(k, str) and "-" in k and isinstance(v, dict):
            by_code[k] = v
    return by_code


def extract_action_definition(action_block: dict) -> str:
    if not isinstance(action_block, dict):
        return ""
    return (
        action_block.get("definition")
        or action_block.get("action_definition")
        or action_block.get("description")
        or ""
    )


def extract_action_title(action_block: dict, fallback: str = "") -> str:
    if not isinstance(action_block, dict):
        return fallback
    return action_block.get("title") or action_block.get("name") or fallback


def extract_maturity_level(action_block: dict, fallback: Any = None) -> Any:
    if not isinstance(action_block, dict):
        return fallback
    return action_block.get("maturity_level") or action_block.get("level") or fallback


def extract_cross_reference(action_block: dict) -> str:
    if not isinstance(action_block, dict):
        return ""
    return action_block.get("cross_reference") or action_block.get("Cross_Reference") or ""


def extract_procedures(action_block: dict) -> List[dict]:
    if not isinstance(action_block, dict):
        return []
    procs = action_block.get("procedures")
    if isinstance(procs, list):
        return [p for p in procs if isinstance(p, dict)]
    return []


def extract_proc_title(proc: dict, fallback: str = "") -> str:
    return proc.get("name") or proc.get("title") or fallback


def extract_proc_recs_notes(proc: dict) -> List[str]:
    out: List[str] = []
    recs = proc.get("recommendations") or []
    notes = proc.get("notes") or []
    if isinstance(recs, list):
        out.extend([str(x) for x in recs if x and str(x).strip()])
    if isinstance(notes, list):
        out.extend([str(x) for x in notes if x and str(x).strip()])
    return out


# =========================================================
# BATCH GENERATION with caches
# =========================================================

def build_batch_prompt(items: List[dict], kind: str) -> str:
    minimal = [{"id": it["id"], "prompt": it["prompt"]} for it in items]
    payload = json.dumps(minimal, ensure_ascii=False, indent=2)

    return f"""
You will generate {kind} texts.

Rules:
- For each item, follow its embedded instructions precisely.
- Return ONLY valid JSON array (no markdown, no commentary).
- Each output element must be: {{ "id": "...", "text": "..." }}
- The response MUST start with "[" and end with "]".

ITEMS:
{payload}
""".strip()


def apply_batch_cache(items: List[dict], cache: Dict[str, str]) -> Tuple[List[dict], Dict[str, str]]:
    to_send: List[dict] = []
    hits: Dict[str, str] = {}
    for it in items:
        ck = it.get("cache_key")
        if ck and ck in cache:
            hits[it["id"]] = cache[ck]
        else:
            to_send.append(it)
    return to_send, hits


def update_batch_cache(items_sent: List[dict], patch_list: List[dict], cache: Dict[str, str]):
    by_id = {p.get("id"): p.get("text") for p in patch_list if isinstance(p, dict)}
    for it in items_sent:
        iid = it["id"]
        text = by_id.get(iid)
        if text is None:
            continue
        ck = it.get("cache_key")
        if ck:
            cache[ck] = text


# =========================================================
# DOMAIN BUILD
# =========================================================

def build_domain_bundle(
    domain_id: str,
    model: str,
    pdf_lookup: Dict[str, str],
    context_cache: Dict[str, str],
    master_cache: Dict[str, str],
    case_cache: Dict[str, str],
    items_per_call: int
) -> Optional[dict]:

    tree_path, action_path = find_domain_files(domain_id)
    if not tree_path.exists():
        print(f"[SKIP] Missing tree: {tree_path.name}")
        return None

    tree = safe_read_json(tree_path)
    if not tree:
        print(f"[SKIP] Invalid tree JSON: {tree_path.name}")
        return None

    questions = extract_questions(tree)
    domain_meta = extract_domain_metadata(tree, domain_id)

    scores_possible, actions_by_score, referenced_actions = build_actions_by_score(questions)

    # Domain contexto (cache)
    objectives = extract_objectives(questions)
    contexto_key = sha256_str(domain_meta["acronym"] + "\n" + stable_json_dumps(objectives))
    contexto = context_cache.get(contexto_key)
    if not contexto:
        prompt = build_domain_context_prompt(domain_meta["name"], objectives)
        contexto = gpt_chat(model, [{"role": "user", "content": prompt}], temperature=0.2)
        context_cache[contexto_key] = contexto

    # Action catalog lookup
    action_catalog_by_code: Dict[str, dict] = {}
    if action_path:
        action_catalog_by_code = load_action_catalog(action_path)

    actions_out: List[dict] = []

    for action_code in referenced_actions:
        ab = action_catalog_by_code.get(action_code, {})
        action_title = extract_action_title(ab, fallback="")
        action_definition = extract_action_definition(ab) or ""
        maturity_level = extract_maturity_level(ab, fallback=None)
        cross_ref = extract_cross_reference(ab)
        theory_context = resolve_theory_context(cross_ref, pdf_lookup)

        procs = extract_procedures(ab)

        procedures_out: List[dict] = []
        master_items: List[dict] = []
        case_items: List[dict] = []

        if procs:
            for pi, proc in enumerate(procs, start=1):
                proc_title = extract_proc_title(proc, fallback=f"Procedure {pi}")
                recs_notes = extract_proc_recs_notes(proc)

                master_input_obj = {
                    "domain": domain_meta["name"],
                    "action_code": action_code,
                    "action_definition": action_definition,
                    "maturity_level": maturity_level,
                    "procedure_title": proc_title,
                    "recs_notes": recs_notes,
                    "theory_context": theory_context[:MAX_CONTEXT_CHARS],
                    "procedure_n": pi
                }
                master_key = sha256_str(stable_json_dumps(master_input_obj))

                master_prompt = build_prompt_1(
                    theory_context=theory_context,
                    domain=domain_meta["name"],
                    action_code=action_code,
                    action_definition=action_definition,
                    maturity_level=maturity_level,
                    procedure_title=proc_title,
                    recommendations_and_notes=recs_notes,
                    procedure_n=pi
                )

                master_items.append({
                    "id": f"{action_code}.p{pi}.master",
                    "cache_key": master_key,
                    "prompt": master_prompt,
                    "procedure_n": pi,
                    "procedure_title": proc_title
                })

                procedures_out.append({
                    "procedure_n": pi,
                    "procedure_title": proc_title,
                    "procedure_master_text": None,
                    "simulated_case": None
                })

        # Prompt 1
        to_send_master, hits_master = apply_batch_cache(master_items, master_cache)

        if hits_master:
            for po in procedures_out:
                pid = f"{action_code}.p{po['procedure_n']}.master"
                if pid in hits_master:
                    po["procedure_master_text"] = hits_master[pid]

        if to_send_master:
            for batch in chunk_list(to_send_master, max(1, items_per_call)):
                prompt_batch = build_batch_prompt(batch, kind="procedure master")
                patch = call_gpt_json_array(
                    model=model,
                    prompt=prompt_batch,
                    label=f"{domain_meta['acronym']} {action_code} Prompt1 batch ({len(batch)})",
                    repair_hint="Return ONLY valid JSON array. Do not include markdown."
                )
                if not patch:
                    print(f"[WARN] Prompt1 batch failed: {domain_meta['acronym']} {action_code}")
                    continue

                update_batch_cache(batch, patch, master_cache)

                by_id = {p.get("id"): p.get("text") for p in patch if isinstance(p, dict)}
                for po in procedures_out:
                    pid = f"{action_code}.p{po['procedure_n']}.master"
                    if po["procedure_master_text"] is None and pid in by_id:
                        po["procedure_master_text"] = by_id[pid]

        # Prompt 2
        for po in procedures_out:
            master_text = po.get("procedure_master_text") or ""
            if not master_text.strip():
                continue

            proc_n = po["procedure_n"]
            proc_title = po["procedure_title"]

            case_input_obj = {
                "domain": domain_meta["name"],
                "action_code": action_code,
                "action_definition": action_definition,
                "maturity_level": maturity_level,
                "procedure_title": proc_title,
                "procedure_master_text": master_text
            }
            case_key = sha256_str(stable_json_dumps(case_input_obj))

            case_prompt = build_prompt_2(
                domain=domain_meta["name"],
                action_code=action_code,
                action_definition=action_definition,
                maturity_level=maturity_level,
                procedure_title=proc_title,
                procedure_master_text=master_text
            )

            case_items.append({
                "id": f"{action_code}.p{proc_n}.case",
                "cache_key": case_key,
                "prompt": case_prompt,
                "procedure_n": proc_n
            })

        to_send_case, hits_case = apply_batch_cache(case_items, case_cache)

        if hits_case:
            for po in procedures_out:
                pid = f"{action_code}.p{po['procedure_n']}.case"
                if pid in hits_case:
                    po["simulated_case"] = hits_case[pid]

        if to_send_case:
            for batch in chunk_list(to_send_case, max(1, items_per_call)):
                prompt_batch = build_batch_prompt(batch, kind="simulated case")
                patch = call_gpt_json_array(
                    model=model,
                    prompt=prompt_batch,
                    label=f"{domain_meta['acronym']} {action_code} Prompt2 batch ({len(batch)})",
                    repair_hint="Return ONLY valid JSON array. Do not include markdown."
                )
                if not patch:
                    print(f"[WARN] Prompt2 batch failed: {domain_meta['acronym']} {action_code}")
                    continue

                update_batch_cache(batch, patch, case_cache)

                by_id = {p.get("id"): p.get("text") for p in patch if isinstance(p, dict)}
                for po in procedures_out:
                    pid = f"{action_code}.p{po['procedure_n']}.case"
                    if po["simulated_case"] is None and pid in by_id:
                        po["simulated_case"] = by_id[pid]

        actions_out.append({
            "action_code": action_code,
            "action_title": action_title,
            "action_definition": action_definition,
            "maturity_level": maturity_level,
            "procedures": procedures_out
        })

    # FINAL BUNDLE (no local paths)
    bundle = {
        "domain": {
            "acronym": domain_meta["acronym"],
            "name": domain_meta["name"],
            "description": domain_meta["description"]
        },
        "contexto": contexto,
        "scores_possiveis": scores_possible,
        "actions_by_score": actions_by_score,
        "actions": actions_out,
        "metadata": {
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "model": model
        }
    }

    return bundle


# =========================================================
# MAIN
# =========================================================

def list_domains_from_original() -> List[str]:
    if not TREE_ORIGINAL_DIR.exists():
        return []
    out = []
    for p in TREE_ORIGINAL_DIR.glob("*_tree_action_cluster.json"):
        name = p.name.replace("_tree_action_cluster.json", "")
        if name:
            out.append(name)
    return sorted(out)


def main():
    parser = argparse.ArgumentParser(description="DOMMx domain bundle builder")
    parser.add_argument("--domains", nargs="*", help="Domain acronyms to process (e.g., DG DQ DMD). If omitted, process all.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"OpenAI model (default: {DEFAULT_MODEL})")
    parser.add_argument("--workers", type=int, default=DEFAULT_MAX_WORKERS, help=f"Parallel workers (default: {DEFAULT_MAX_WORKERS})")
    parser.add_argument("--items-per-call", type=int, default=DEFAULT_ITEMS_PER_CALL, help=f"Batch size per GPT call (default: {DEFAULT_ITEMS_PER_CALL})")
    args = parser.parse_args()

    ensure_dir(CACHE_DIR)
    ensure_dir(TREE_IMPROVED_DIR)

    pdf_cache = safe_read_json(PDF_CACHE_PATH) or {}
    pdf_lookup = build_pdf_lookup(pdf_cache)

    context_cache = _load_cache(DOMAIN_CONTEXT_CACHE_PATH)
    master_cache = _load_cache(PROCEDURE_MASTER_CACHE_PATH)
    case_cache = _load_cache(PROCEDURE_CASE_CACHE_PATH)

    domains = args.domains or list_domains_from_original()
    if not domains:
        print("[DONE] No domains found.")
        return

    print(f"[INFO] Domains: {domains}")
    print(f"[INFO] Model: {args.model} | Workers: {args.workers} | Items/call: {args.items_per_call}")

    results: Dict[str, dict] = {}
    errors: Dict[str, str] = {}

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        futs = {
            ex.submit(
                build_domain_bundle,
                domain_id=d,
                model=args.model,
                pdf_lookup=pdf_lookup,
                context_cache=context_cache,
                master_cache=master_cache,
                case_cache=case_cache,
                items_per_call=args.items_per_call
            ): d
            for d in domains
        }

        for fut in as_completed(futs):
            d = futs[fut]
            try:
                bundle = fut.result()
                if not bundle:
                    errors[d] = "bundle_not_generated"
                    continue

                out_path = TREE_IMPROVED_DIR / f"{d}_domain_bundle.json"
                save_json(out_path, bundle)

                results[d] = {
                    "output_file": out_path.name,
                    "actions_count": len(bundle.get("actions", []))
                }
                print(f"[OK] {d} -> {out_path.name} | actions={results[d]['actions_count']}")

            except Exception as e:
                errors[d] = str(e)
                print(f"[ERROR] {d}: {e}")

    _save_cache(DOMAIN_CONTEXT_CACHE_PATH, context_cache)
    _save_cache(PROCEDURE_MASTER_CACHE_PATH, master_cache)
    _save_cache(PROCEDURE_CASE_CACHE_PATH, case_cache)

    summary = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "domains_requested": domains,
        "results": results,
        "errors": errors
    }
    save_json(TREE_IMPROVED_DIR / "_bundle_build_summary.json", summary)

    print("\n[DONE] Summary:")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()