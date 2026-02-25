# utils/theory_cluster.py
# V3 FINAL DEFINITIVO (Performance Master)
# - Orquestra via data/general/flow.yaml (ordem e arquivos por domínio)
# - Output por domínio: data/global/theory/<DOMAIN>_theory_cluster_output.json
# - Caches por domínio em: data/global/theory/_cache/
# - PDF cache GLOBAL em: data/global/theory/_cache/pdf_pages_cache.json
# - Topic excerpts cache GLOBAL em: data/global/theory/_cache/topic_excerpts_cache.json
# - CTRL+C: salva parcial e sai

import os
import json
import time
import yaml
import argparse
import random
import re
import signal
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv
from openai import OpenAI
from PyPDF2 import PdfReader

# =========================================================
# BASE DIR / PATHS (alinhado com extract_theory.py)
# =========================================================

BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"
GENERAL_DIR = DATA_DIR / "general"
FLOW_PATH = GENERAL_DIR / "flow.yaml"

DOMAINS_DIR = DATA_DIR / "domains"

THEORY_DIR = DATA_DIR / "global" / "theory"
OUTPUT_DIR = THEORY_DIR
CACHE_DIR = THEORY_DIR / "_cache"
PDF_DIR = THEORY_DIR / "PDFs"

# Cache GLOBAL (Opção A)
PDF_PAGES_CACHE = CACHE_DIR / "pdf_pages_cache.json"
TOPIC_EXCERPTS_CACHE = CACHE_DIR / "topic_excerpts_cache.json"

# =========================================================
# RUNTIME DEFAULTS
# =========================================================

DEFAULT_LANGUAGE = "us"
DEFAULT_MODEL_DT = "gpt-4o-mini"
DEFAULT_MODEL_AC = "gpt-4o-mini"

# Ajuste fino: API externa, não exagera
DEFAULT_MAX_WORKERS = 6
DEFAULT_BATCH_SIZE = 10

# Excerpts por item para “grounding”
MAX_EXCERPTS_PER_ITEM = 6
MAX_EXCERPT_CHARS = 900

# =========================================================
# CTRL+C (salvar parcial)
# =========================================================

signal.signal(signal.SIGINT, signal.SIG_DFL)

# =========================================================
# HELPERS: logging / progress
# =========================================================

def now_ts() -> str:
    return time.strftime("%H:%M:%S")

def log(msg: str) -> None:
    print(f"[{now_ts()}] {msg}", flush=True)

def norm_space(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

def progress_line(prefix: str, done: int, total: int, extra: str = "") -> None:
    if total <= 0:
        return
    pct = int((done / total) * 100)
    tail = f" | {extra}" if extra else ""
    print(f"\r[{now_ts()}] {prefix}: {done}/{total} ({pct}%)" + tail + " " * 10, end="", flush=True)
    if done >= total:
        print("", flush=True)

# =========================================================
# YAML / JSON IO
# =========================================================

def load_yaml(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path: Path, obj: Any) -> None:
    ensure_dir(path.parent)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    tmp.replace(path)

# =========================================================
# DOMAIN PATHS (output + caches por domínio)
# =========================================================

def domain_paths(domain: str) -> Dict[str, Path]:
    domain = domain.upper().strip()
    out_json = OUTPUT_DIR / f"{domain}_theory_cluster_output.json"
    cache_json = CACHE_DIR / f"{domain}_theory_cluster_cache.json"          # Hash_Key -> generated text payload
    distinct_topics_json = CACHE_DIR / f"{domain}_distinct_topics.json"     # distinct topics for this domain run
    return {
        "out_json": out_json,
        "cache_json": cache_json,
        "distinct_topics_json": distinct_topics_json,
    }

# =========================================================
# FLOW: ordered domains
# =========================================================

def get_flow_domains(flow: Dict[str, Any]) -> List[Dict[str, Any]]:
    items = flow.get("Domain_flow") or []
    items = sorted(items, key=lambda x: int(x.get("sequence", 9999)))
    return items

def select_domains(flow_items: List[Dict[str, Any]], domain_filter: Optional[str]) -> List[Dict[str, Any]]:
    if not domain_filter:
        return flow_items
    wanted = domain_filter.upper().strip()
    picked = [d for d in flow_items if str(d.get("acronym", "")).upper().strip() == wanted]
    return picked

# =========================================================
# DOMAIN YAML PATHS
# =========================================================

def resolve_domain_yaml_paths(language: str, flow_domain_item: Dict[str, Any]) -> Tuple[Path, Path]:
    files = flow_domain_item.get("files") or {}
    dt_file = files.get("decision_tree")
    ac_file = files.get("action_catalog")
    if not dt_file or not ac_file:
        raise ValueError(f"Flow domain item missing files decision_tree/action_catalog: {flow_domain_item}")

    # padrão do repo: data/domains/<language>/<yaml>
    dt_path = DOMAINS_DIR / language / dt_file
    ac_path = DOMAINS_DIR / language / ac_file
    return dt_path, ac_path

# =========================================================
# YAML PARSERS -> flat rows join-friendly
# =========================================================

def build_decision_tree_rows(domain: str, dt_yaml: Dict[str, Any]) -> List[Dict[str, Any]]:
    domain = domain.upper()
    rows: List[Dict[str, Any]] = []

    # Detecta onde estão as questions
    questions = (
        dt_yaml.get("questions")
        or dt_yaml.get("decision_tree", {}).get("questions")
        or dt_yaml.get("DecisionTree", {}).get("questions")
        or {}
    )

    if not isinstance(questions, dict):
        return rows

    for q_key, q_data in questions.items():
        q = str(q_key).strip()

        explanation = norm_space(q_data.get("explanation") or "")
        objective = norm_space(q_data.get("objective") or "")
        cross_ref = norm_space(q_data.get("cross_reference") or "")

        score_map = q_data.get("score_action_mapping") or {}
        if not isinstance(score_map, dict):
            continue

        for score_key, mapping in score_map.items():
            try:
                score = int(str(score_key))
            except Exception:
                continue

            mapping = mapping or {}
            action_code = norm_space(mapping.get("action_code") or "")
            action_desc = norm_space(mapping.get("description") or mapping.get("action_description") or "")

            row = {
                "Type": "decision_tree",
                "Domain": domain,
                "Question": q,
                "Score": score,
                "Action_Code": action_code,
                "Join_Key": f"{domain}|{q}|{score}",
                "Action_Join_Key": f"{domain}|{action_code}" if action_code else "",
                "Hash_Key": f"\"decision tree\"|\"{domain}\"|\"{q}\"|\"{score}\"|\"{action_code}\"",
                "Cross_Reference": cross_ref,
                "Action_Description": action_desc,
                "Explanation": explanation,
                "Objective": objective,
                "Topic_Keys": [],
                "Text": "",
            }

            rows.append(row)

    return rows

def build_action_catalog_rows(domain: str, ac_yaml: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Espera estrutura:
      action_catalog:
        DG-01:
          title: ...
          procedures:
            1: { name, prerequisite, deliverable, recommendations, notes, ...}
            2: ...
    """
    domain = domain.upper()
    root = ac_yaml.get("action_catalog") or ac_yaml.get("ActionCatalog") or ac_yaml.get("catalog") or ac_yaml
    rows: List[Dict[str, Any]] = []

    if not isinstance(root, dict):
        return rows

    for action_code, action_payload in root.items():
        action_code = str(action_code).strip()
        action_payload = action_payload or {}
        action_title = norm_space(action_payload.get("title") or action_payload.get("Action_Title") or action_payload.get("name") or "")

        procs = action_payload.get("procedures") or action_payload.get("Procedures") or {}
        if isinstance(procs, list):
            # se vier lista, tenta mapear por index+1
            procs = {i + 1: p for i, p in enumerate(procs)}

        if not isinstance(procs, dict):
            continue

        for proc_key, proc_payload in procs.items():
            try:
                proc_num = int(str(proc_key).strip())
            except Exception:
                continue

            proc_payload = proc_payload or {}
            proc_name = norm_space(proc_payload.get("name") or proc_payload.get("Procedure_Name") or "")
            prereq = norm_space(proc_payload.get("prerequisite") or proc_payload.get("Prerequisite") or "")
            deliverable = norm_space(proc_payload.get("deliverable") or proc_payload.get("Deliverable") or "")

            recs = proc_payload.get("recommendations") or proc_payload.get("Recommendations") or []
            notes = proc_payload.get("notes") or proc_payload.get("Notes") or []
            topic_keys = proc_payload.get("topic_keys") or proc_payload.get("Topic_Keys") or []

            if isinstance(recs, str):
                recs = [recs]
            if isinstance(notes, str):
                notes = [notes]
            if isinstance(topic_keys, str):
                topic_keys = [topic_keys]

            recs = [norm_space(x) for x in recs if norm_space(x)]
            notes = [norm_space(x) for x in notes if norm_space(x)]
            topic_keys = [norm_space(x) for x in topic_keys if norm_space(x)]

            row = {
                "Type": "action_catalog",
                "Domain": domain,
                "Action_Code": action_code,
                "Procedure": proc_num,
                "Action_Join_Key": f"{domain}|{action_code}",
                "Procedure_Join_Key": f"{domain}|{action_code}|{proc_num}",
                "Hash_Key": f"\"action catalog\"|\"{domain}\"|\"{action_code}\"|\"{proc_num}\"",
                "Action_Title": action_title,
                "Procedure_Name": proc_name,
                "Prerequisite": prereq,
                "Deliverable": deliverable,
                "Recommendations": recs,
                "Notes": notes,
                "Topic_Keys": topic_keys,
                "Text": "",  # gerado pela IA
            }
            rows.append(row)

    return rows

# =========================================================
# TOPICS: distinct + stable extraction (sem regex frágil)
# =========================================================

def extract_candidate_topics(text: str) -> List[str]:
    """
    Extrai temas prováveis de strings tipo:
      "DMBOK2 Chapter 3.2, p. 55-57"
      "DCAM capability scoping"
      "CMMI process areas"
    Regra: sem regex com group obrigatório.
    """
    t = norm_space(text)
    if not t:
        return []

    out: List[str] = []

    # pega padrões "DMBOK2 Chapter X" / "DAMA-DMBOK2 Chapter X"
    for m in re.finditer(r"\b(DAMA\-DMBOK2|DMBOK2)\s+Chapter\s+([0-9]+(?:\.[0-9]+)?)\b", t, flags=re.I):
        fw = m.group(1).upper().replace("DAMA-", "")
        ch = m.group(2)
        out.append(f"{fw} Chapter {ch}")

    # DCAM / CMMI / GDPR / IDGC palavras-chave
    keywords = [
        "DCAM capability scoping",
        "DCAM Governance",
        "DCAM Ownership",
        "DCAM Measurement",
        "CMMI process areas",
        "GDPR",
        "IDGC",
        "Policy",
        "Principles",
        "Stewardship",
        "Roles and responsibilities",
        "Decision authority",
        "Lifecycle checkpoints",
        "Metadata",
        "Data Quality",
        "Audit",
        "Compliance",
    ]
    low = t.lower()
    for k in keywords:
        if k.lower() in low:
            out.append(k)

    # dedupe mantendo ordem
    seen = set()
    res = []
    for x in out:
        x = norm_space(x)
        if x and x not in seen:
            seen.add(x)
            res.append(x)
    return res

def collect_distinct_topics(domain: str, dt_rows: List[Dict[str, Any]], ac_rows: List[Dict[str, Any]]) -> List[str]:
    topics: List[str] = []

    for r in dt_rows:
        for tk in (r.get("Topic_Keys") or []):
            topics.extend(extract_candidate_topics(tk) or [tk])
        topics.extend(extract_candidate_topics(r.get("Cross_Reference") or ""))
        topics.extend(extract_candidate_topics(r.get("Action_Description") or ""))

    for r in ac_rows:
        for tk in (r.get("Topic_Keys") or []):
            topics.extend(extract_candidate_topics(tk) or [tk])
        for rec in (r.get("Recommendations") or []):
            topics.extend(extract_candidate_topics(rec) or [rec])
        for nt in (r.get("Notes") or []):
            topics.extend(extract_candidate_topics(nt) or [nt])

    # normalize and unique
    uniq = []
    seen = set()
    for t in topics:
        t = norm_space(t)
        if not t:
            continue
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq

# =========================================================
# PDF CACHE: pages text (GLOBAL)
# =========================================================

def pdf_fingerprint(path: Path) -> str:
    st = path.stat()
    return f"{path.name}|{int(st.st_mtime)}|{st.st_size}"

def load_pdf_pages_cache() -> Dict[str, Any]:
    return load_json(PDF_PAGES_CACHE, default={"_meta": {"created_utc": None}, "pdfs": {}})

def save_pdf_pages_cache(cache: Dict[str, Any]) -> None:
    cache.setdefault("_meta", {})["updated_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    save_json(PDF_PAGES_CACHE, cache)

def extract_pdf_pages_text(path: Path) -> List[str]:
    reader = PdfReader(str(path))
    pages = []
    for p in reader.pages:
        try:
            txt = p.extract_text() or ""
        except Exception:
            txt = ""
        pages.append(norm_space(txt))
    return pages

def ensure_pdf_pages_cached(clear_pdf_cache: bool = False) -> Dict[str, List[str]]:
    ensure_dir(CACHE_DIR)
    cache = load_pdf_pages_cache()
    if clear_pdf_cache and PDF_PAGES_CACHE.exists():
        log("Clearing GLOBAL PDF cache...")
        cache = {"_meta": {}, "pdfs": {}}

    pdfs = {}
    pdf_files = sorted(PDF_DIR.glob("*.pdf"))
    log(f"PDF extraction using PyPDF2 | PDFs found: {len(pdf_files)}")

    for idx, pdf_path in enumerate(pdf_files, start=1):
        fp = pdf_fingerprint(pdf_path)
        entry = (cache.get("pdfs") or {}).get(pdf_path.name)
        if entry and entry.get("fingerprint") == fp and isinstance(entry.get("pages"), list) and len(entry["pages"]) > 0:
            pages = entry["pages"]
        else:
            pages = extract_pdf_pages_text(pdf_path)
            cache.setdefault("pdfs", {})[pdf_path.name] = {"fingerprint": fp, "pages": pages}
            log(f"PDF cached: {pdf_path.name} | pages={len(pages)}")

        pdfs[pdf_path.name] = pages
        progress_line("PDF cache", idx, len(pdf_files), extra=pdf_path.name)

    save_pdf_pages_cache(cache)
    return pdfs

# =========================================================
# TOPIC EXCERPTS CACHE (GLOBAL)
# =========================================================

def load_topic_excerpts_cache() -> Dict[str, Any]:
    return load_json(TOPIC_EXCERPTS_CACHE, default={"_meta": {}, "topics": {}})

def save_topic_excerpts_cache(cache: Dict[str, Any]) -> None:
    cache.setdefault("_meta", {})["updated_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    save_json(TOPIC_EXCERPTS_CACHE, cache)

def build_excerpts_for_topic(topic: str, pdf_pages: Dict[str, List[str]]) -> List[Dict[str, str]]:
    """
    Busca simples e rápida por substring (sem vetor).
    Retorna lista [{pdf, excerpt}]
    """
    t = norm_space(topic)
    if not t:
        return []

    # tokens para busca: remove pontuação excessiva, reduz
    token = re.sub(r"[^a-zA-Z0-9\.\-\s]", " ", t).strip()
    token_low = token.lower()
    if len(token_low) < 4:
        return []

    hits: List[Dict[str, str]] = []

    for pdf_name, pages in pdf_pages.items():
        found = 0
        for i, page_txt in enumerate(pages):
            if not page_txt:
                continue
            if token_low in page_txt.lower():
                # excerpt pequeno para prompt
                start = page_txt.lower().find(token_low)
                a = max(0, start - 250)
                b = min(len(page_txt), start + 650)
                excerpt = page_txt[a:b]
                excerpt = excerpt[:MAX_EXCERPT_CHARS]
                hits.append({"pdf": pdf_name, "excerpt": excerpt})
                found += 1
                if found >= 3:
                    break

    # limita
    return hits[:8]

def ensure_topic_excerpts(topics: List[str], pdf_pages: Dict[str, List[str]], clear_topic_cache: bool = False) -> Dict[str, List[Dict[str, str]]]:
    ensure_dir(CACHE_DIR)
    cache = load_topic_excerpts_cache()
    if clear_topic_cache and TOPIC_EXCERPTS_CACHE.exists():
        log("Clearing GLOBAL topic excerpts cache...")
        cache = {"_meta": {}, "topics": {}}

    out: Dict[str, List[Dict[str, str]]] = {}
    total = len(topics)

    for i, topic in enumerate(topics, start=1):
        k = norm_space(topic)
        if not k:
            continue
        if k in cache.get("topics", {}):
            out[k] = cache["topics"][k]
        else:
            ex = build_excerpts_for_topic(k, pdf_pages)
            cache.setdefault("topics", {})[k] = ex
            out[k] = ex
        progress_line("Topic index", i, total, extra=k[:40])

    save_topic_excerpts_cache(cache)
    return out

def excerpts_for_item(topic_keys: List[str], topic_excerpts: Dict[str, List[Dict[str, str]]]) -> List[Dict[str, str]]:
    res: List[Dict[str, str]] = []
    for tk in topic_keys:
        tk = norm_space(tk)
        if not tk:
            continue
        for e in topic_excerpts.get(tk, []):
            res.append(e)
            if len(res) >= MAX_EXCERPTS_PER_ITEM:
                return res
    return res[:MAX_EXCERPTS_PER_ITEM]

# =========================================================
# OPENAI CALLS (retry + cache by Hash_Key)
# =========================================================

def openai_client() -> OpenAI:
    load_dotenv(BASE_DIR / ".env")
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def backoff_sleep(attempt: int) -> None:
    # jitter
    base = min(30, (2 ** attempt))
    time.sleep(base + random.uniform(0.2, 1.2))

def call_gpt_text(
    client: OpenAI,
    model: str,
    system: str,
    user: str,
    max_retries: int = 5,
) -> str:
    last_err = None
    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=model,
                temperature=0,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            txt = (resp.choices[0].message.content or "").strip()
            return txt
        except Exception as e:
            last_err = e
            backoff_sleep(attempt)
    raise RuntimeError(f"GPT failed after retries: {last_err}")

# =========================================================
# PROMPTS
# =========================================================

DT_SYSTEM = "You are an expert Data Governance and Data Management practitioner. Return high-quality professional text. No JSON. No apologies."

def dt_user_prompt(row: Dict[str, Any], excerpts: List[Dict[str, str]]) -> str:
    domain = row.get("Domain", "")
    q = row.get("Question", "")
    score = row.get("Score", "")
    action_code = row.get("Action_Code", "")
    cross = row.get("Cross_Reference", "")
    desc = row.get("Action_Description", "")

    ex_block = ""
    if excerpts:
        lines = []
        for e in excerpts:
            lines.append(f"- Source: {e.get('pdf')} | Excerpt: {e.get('excerpt')}")
        ex_block = "\n\nAuthoritative excerpts (use as grounding, do not quote verbatim long):\n" + "\n".join(lines)

    return f"""
Write a report-ready explanation for a maturity recommendation mapping.

Context:
- Type: decision tree
- Domain: {domain}
- Question: {q}
- Maturity Score: {score}
- Action Code: {action_code}
- Cross References: {cross}
- Action Description: {desc}

Instructions:
1) Write 2 to 4 paragraphs, maximum 5.
2) Explain why this action code is the right next step for this maturity score.
3) Explicitly connect the explanation to the cross references and the action description.
4) Include practical intent: what must change in the organization and what outcome is expected.
5) Keep it professional, concise, and contextualized. No bullet lists unless absolutely needed.

{ex_block}
""".strip()

AC_SYSTEM = (
    "You are an expert Data Governance and Data Management practitioner and solution architect. "
    "Produce prescriptive, step-by-step practitioner guidance. No JSON. No theoretical essay."
)

def ac_user_prompt(row: Dict[str, Any], excerpts: List[Dict[str, str]]) -> str:
    domain = row.get("Domain", "")
    action_code = row.get("Action_Code", "")
    proc = row.get("Procedure", "")
    action_title = row.get("Action_Title", "")
    proc_name = row.get("Procedure_Name", "")
    prereq = row.get("Prerequisite", "")
    deliverable = row.get("Deliverable", "")
    recs = row.get("Recommendations") or []
    notes = row.get("Notes") or []
    topic_keys = row.get("Topic_Keys") or []

    rec_block = "\n".join([f"- {r}" for r in recs]) if recs else "- (none)"
    notes_block = "\n".join([f"- {n}" for n in notes]) if notes else "- (none)"
    topics_block = ", ".join(topic_keys) if topic_keys else "(none)"

    ex_block = ""
    if excerpts:
        lines = []
        for e in excerpts:
            lines.append(f"- Source: {e.get('pdf')} | Excerpt: {e.get('excerpt')}")
        ex_block = "\n\nAuthoritative excerpts (use as grounding, avoid long direct quotes):\n" + "\n".join(lines)

    return f"""
You are an expert Data Governance and Data Management practitioner.

Your task is to construct prescriptive procedural guidance based strictly on authoritative framework content.

Action context:
- Domain: {domain}
- Action Code: {action_code}
- Procedure: {proc}
- Action Title: {action_title}
- Procedure Name: {proc_name}
- Prerequisite: {prereq}
- Deliverable: {deliverable}

Recommendations (MUST be used as requirements to shape the procedure):
{rec_block}

Notes (MUST be used to add practitioner nuance and adoption guidance):
{notes_block}

Topic Keys:
{topics_block}

Instructions:
1) Produce a recipe-like step-by-step procedure a practitioner can follow.
2) The procedure must show how the references fit into concrete actions.
3) Include intermediate outputs for key steps, and finish with the deliverable structure.
4) Include adoption and governance mechanics (roles, decision authority, stewardship checkpoints) when relevant.
5) Do NOT write a generic framework explanation.
6) Do NOT just restate the recommendation list.
7) Output must be LONGER: 2 to 4 paragraphs total minimum, maximum 5, PLUS a clear numbered step list (5 to 9 steps).
8) Keep the steps concrete: verbs, artifacts, approvals, checkpoints, owners.

Expected output format:
Action Title: ...
Procedure Name: ...
Prerequisite: ...
Deliverable: ...

Paragraphs (2-4):
<write here>

Steps:
1) ...
   - Actions: ...
   - Intermediate Output: ...
2) ...
...

Closing:
<short closing paragraph that reminds how to validate completion>

{ex_block}
""".strip()

# =========================================================
# GENERATION ENGINE (domain-level)
# =========================================================

def load_domain_cache(cache_path: Path) -> Dict[str, Any]:
    return load_json(cache_path, default={"generated": {}, "_meta": {}})

def save_domain_cache(cache_path: Path, cache: Dict[str, Any]) -> None:
    cache.setdefault("_meta", {})["updated_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    save_json(cache_path, cache)

def should_generate_text(row: Dict[str, Any]) -> bool:
    # sempre gera se vazio
    return not norm_space(row.get("Text", ""))

def run_domain_generation(
    client: OpenAI,
    domain_item: Dict[str, Any],
    language: str,
    model_dt: str,
    model_ac: str,
    max_workers: int,
    batch_size: int,
    clear_domain_cache: bool,
    clear_pdf_cache: bool,
    clear_topic_cache: bool,
) -> Dict[str, Any]:
    domain = str(domain_item.get("acronym", "")).upper().strip()
    dp = domain_paths(domain)

    dt_path, ac_path = resolve_domain_yaml_paths(language, domain_item)
    if not dt_path.exists():
        raise FileNotFoundError(f"Decision tree YAML not found: {dt_path}")
    if not ac_path.exists():
        raise FileNotFoundError(f"Action catalog YAML not found: {ac_path}")

    # load yaml
    dt_yaml = load_yaml(dt_path)
    ac_yaml = load_yaml(ac_path)

    dt_rows = build_decision_tree_rows(domain, dt_yaml)
    ac_rows = build_action_catalog_rows(domain, ac_yaml)

    # pdf cache + topic excerpts
    pdf_pages = ensure_pdf_pages_cached(clear_pdf_cache=clear_pdf_cache)

    distinct_topics = collect_distinct_topics(domain, dt_rows, ac_rows)
    save_json(dp["distinct_topics_json"], {"Domain": domain, "topics": distinct_topics})

    topic_excerpts = ensure_topic_excerpts(distinct_topics, pdf_pages, clear_topic_cache=clear_topic_cache)

    # load domain cache (Hash_Key -> Text)
    if clear_domain_cache and dp["cache_json"].exists():
        log(f"Clearing domain cache: {dp['cache_json'].name}")
        cache = {"generated": {}, "_meta": {}}
    else:
        cache = load_domain_cache(dp["cache_json"])

    generated = cache.setdefault("generated", {})

    # prepare tasks
    dt_todo = [r for r in dt_rows if should_generate_text(r)]
    ac_todo = [r for r in ac_rows if should_generate_text(r)]

    total_dt = len(dt_todo)
    total_ac = len(ac_todo)

    log(f"Domain={domain} | decision_tree rows={len(dt_rows)} (to-gen={total_dt}) | action_catalog rows={len(ac_rows)} (to-gen={total_ac})")

    # apply cached texts when present
    for r in dt_rows:
        hk = r["Hash_Key"]
        if hk in generated and norm_space(generated[hk].get("Text", "")):
            r["Text"] = generated[hk]["Text"]

    for r in ac_rows:
        hk = r["Hash_Key"]
        if hk in generated and norm_space(generated[hk].get("Text", "")):
            r["Text"] = generated[hk]["Text"]

    # refresh todo after cache apply
    dt_todo = [r for r in dt_rows if should_generate_text(r)]
    ac_todo = [r for r in ac_rows if should_generate_text(r)]

    # executor
    def worker_generate(kind: str, row: Dict[str, Any]) -> Tuple[str, str]:
        hk = row["Hash_Key"]
        # topic_keys base: row Topic_Keys + derive from Cross/Recommendations/Notes for better grounding
        tks: List[str] = []
        if kind == "dt":
            tks.extend(row.get("Topic_Keys") or [])
            tks.extend(extract_candidate_topics(row.get("Cross_Reference") or ""))
            tks.extend(extract_candidate_topics(row.get("Action_Description") or ""))
            sys = DT_SYSTEM
            ex = excerpts_for_item([norm_space(x) for x in tks if norm_space(x)], topic_excerpts)
            usr = dt_user_prompt(row, ex)
            txt = call_gpt_text(client, model_dt, sys, usr)
        else:
            tks.extend(row.get("Topic_Keys") or [])
            for rec in (row.get("Recommendations") or []):
                tks.extend(extract_candidate_topics(rec))
            for nt in (row.get("Notes") or []):
                tks.extend(extract_candidate_topics(nt))
            sys = AC_SYSTEM
            ex = excerpts_for_item([norm_space(x) for x in tks if norm_space(x)], topic_excerpts)
            usr = ac_user_prompt(row, ex)
            txt = call_gpt_text(client, model_ac, sys, usr)

        return hk, txt

    # batching helper
    def process_in_batches(kind: str, todo: List[Dict[str, Any]]) -> None:
        if not todo:
            return
        total = len(todo)
        done = 0

        # split into batches
        batches = [todo[i:i + batch_size] for i in range(0, len(todo), batch_size)]
        for bi, batch in enumerate(batches, start=1):
            log(f"{kind.upper()} batch {bi}/{len(batches)} | size={len(batch)}")
            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                futs = {ex.submit(worker_generate, kind, row): row for row in batch}
                for fut in as_completed(futs):
                    row = futs[fut]
                    hk = row["Hash_Key"]
                    try:
                        hk2, txt = fut.result()
                        row["Text"] = txt
                        generated[hk2] = {"Text": txt}
                    except KeyboardInterrupt:
                        raise
                    except Exception as e:
                        # registra erro, mas não para tudo
                        generated[hk] = {"Text": "", "Error": str(e)}
                    done += 1
                    progress_line(f"{kind.upper()} gen", done, total, extra=f"batch {bi}/{len(batches)}")
            # salva cache a cada batch
            save_domain_cache(dp["cache_json"], cache)

    # run generations (ordem: decision_tree depois action_catalog)
    try:
        if dt_todo:
            process_in_batches("dt", dt_todo)
        if ac_todo:
            process_in_batches("ac", ac_todo)
    except KeyboardInterrupt:
        log("CTRL+C detected. Saving partial outputs and exiting gracefully...")

    # montar output do domínio
    out_obj = {
        "decision_tree": dt_rows,
        "action_catalog": ac_rows,
        "meta": {
            "language": language,
            "models": {"decision_tree": model_dt, "action_catalog": model_ac},
            "flow_path": str(FLOW_PATH),
            "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "domain": domain,
            "domain_name": domain_item.get("name"),
            "domain_sequence": domain_item.get("sequence"),
        }
    }

    save_json(dp["out_json"], out_obj)
    save_domain_cache(dp["cache_json"], cache)

    log(f"Output saved: {dp['out_json']}")
    log(f"Cache  saved: {dp['cache_json']}")

    return out_obj

# =========================================================
# MAIN
# =========================================================

def main():
    parser = argparse.ArgumentParser(description="DOMMx Theory Cluster (Decision Tree + Action Catalog) - per domain outputs/caches")
    parser.add_argument("--language", default=DEFAULT_LANGUAGE, help="language folder under data/domains (default: us)")
    parser.add_argument("--domain", default=None, help="run only one domain acronym (e.g., DG). If omitted, run all domains from flow.yaml")
    parser.add_argument("--model-dt", default=DEFAULT_MODEL_DT, help="OpenAI model for decision tree text")
    parser.add_argument("--model-ac", default=DEFAULT_MODEL_AC, help="OpenAI model for action catalog text")
    parser.add_argument("--max-workers", type=int, default=DEFAULT_MAX_WORKERS, help="parallel workers")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="batch size for parallel requests")
    parser.add_argument("--clear-cache", action="store_true", help="clear DOMAIN cache before generating")
    parser.add_argument("--clear-pdf-cache", action="store_true", help="clear GLOBAL pdf cache before generating")
    parser.add_argument("--clear-topic-cache", action="store_true", help="clear GLOBAL topic excerpts cache before generating")

    args = parser.parse_args()

    ensure_dir(OUTPUT_DIR)
    ensure_dir(CACHE_DIR)

    language = (args.language or DEFAULT_LANGUAGE).strip()
    domain_filter = (args.domain.strip().upper() if args.domain else None)

    flow = load_yaml(FLOW_PATH)
    flow_items = get_flow_domains(flow)
    selected = select_domains(flow_items, domain_filter)

    if not selected:
        raise ValueError(f"No domains selected. Check --domain={args.domain} and flow.yaml")

    log(f"MODE={'ALL' if not domain_filter else domain_filter} | language={language} | domains={[d.get('acronym') for d in selected]}")
    log(f"Models: DT={args.model_dt} | AC={args.model_ac}")
    log(f"THEORY_DIR: {THEORY_DIR}")
    log(f"Output dir: {OUTPUT_DIR}")
    log(f"Cache  dir: {CACHE_DIR}")
    log("-" * 50)

    client = openai_client()

    results_meta = []
    try:
        for i, domain_item in enumerate(selected, start=1):
            dom = str(domain_item.get("acronym", "")).upper().strip()
            log(f"Running domain {i}/{len(selected)}: {dom}")
            out_obj = run_domain_generation(
                client=client,
                domain_item=domain_item,
                language=language,
                model_dt=args.model_dt,
                model_ac=args.model_ac,
                max_workers=args.max_workers,
                batch_size=args.batch_size,
                clear_domain_cache=args.clear_cache,
                clear_pdf_cache=args.clear_pdf_cache,
                clear_topic_cache=args.clear_topic_cache,
            )
            results_meta.append(out_obj.get("meta", {}))
            log("-" * 50)
    except KeyboardInterrupt:
        log("Stopped by user (CTRL+C).")

    # resumo final
    if results_meta:
        done_domains = [m.get("domain") for m in results_meta if m.get("domain")]
        log(f"Done domains: {done_domains}")

if __name__ == "__main__":
    main()