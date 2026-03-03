# utils/theory_cluster_improve.py
# Purpose
# - Read:  utils/theory-cluster/output/<DOMAIN>_theory_cluster_output.json
# - Write: utils/theory-cluster/output/<DOMAIN>_theory_improved_output.json
# - End to end English
# - Mode: all domains (from flow.yaml) or single domain
# - Focus: report readiness, precision, performance, cache, cost control

import os
import json
import time
import re
import argparse
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv
from openai import OpenAI
import yaml


# =========================================================
# BASE DIR / PATHS aligned with existing theory_cluster.py
# =========================================================

BASE_DIR = Path(__file__).resolve().parent.parent.parent

DATA_DIR = BASE_DIR / "data"
GENERAL_DIR = DATA_DIR / "general"
FLOW_PATH = GENERAL_DIR / "flow.yaml"

THEORY_DIR = BASE_DIR / "utils" / "theory-cluster"
INPUT_DIR = THEORY_DIR / "output" / "cluster"
OUTPUT_DIR = THEORY_DIR / "output" / "improved"
CACHE_DIR = THEORY_DIR / "_cache"

DEFAULT_MODEL_IMPROVE = "gpt-4o-mini"
DEFAULT_MAX_WORKERS = 6
DEFAULT_BATCH_SIZE = 12

# Cache file name pattern
# - Stores improved output per unique fingerprint of inputs to avoid re spending tokens
IMPROVE_CACHE_SUFFIX = "_theory_improve_cache.json"


# =========================================================
# Helpers
# =========================================================

def now_ts() -> str:
    return time.strftime("%H:%M:%S")

def log(msg: str) -> None:
    print(f"[{now_ts()}] {msg}", flush=True)

def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

def norm_space(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

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

def load_yaml(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def sha256_text(s: str) -> str:
    return hashlib.sha256((s or "").encode("utf-8")).hexdigest()

def extract_first_json_object(text: str) -> Optional[Dict[str, Any]]:
    """
    Best effort JSON extraction:
    - Prefer strict json.loads on full string
    - Else extract first {...} block
    """
    t = (text or "").strip()
    if not t:
        return None
    try:
        obj = json.loads(t)
        if isinstance(obj, dict):
            return obj
        return None
    except Exception:
        pass

    m = re.search(r"\{.*\}", t, flags=re.S)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
        if isinstance(obj, dict):
            return obj
    except Exception:
        return None
    return None


# =========================================================
# Domain selection via flow.yaml
# =========================================================

def get_flow_domains(flow: Dict[str, Any]) -> List[Dict[str, Any]]:
    items = flow.get("Domain_flow") or []
    items = sorted(items, key=lambda x: int(x.get("sequence", 9999)))
    return items

def select_domains(flow_items: List[Dict[str, Any]], domain_filter: Optional[str]) -> List[Dict[str, Any]]:
    if not domain_filter:
        return flow_items
    wanted = domain_filter.upper().strip()
    return [d for d in flow_items if str(d.get("acronym", "")).upper().strip() == wanted]

def domain_io_paths(domain: str) -> Tuple[Path, Path, Path]:
    domain = domain.upper().strip()
    in_json = INPUT_DIR / f"{domain}_theory_cluster_output.json"
    out_json = OUTPUT_DIR / f"{domain}_theory_improved_output.json"
    cache_json = CACHE_DIR / f"{domain}{IMPROVE_CACHE_SUFFIX}"
    return in_json, out_json, cache_json


# =========================================================
# Function 1
# - Context_Initial: distinct Objective values where Score == 1 across Q1..Q6
# - Return array entries: [Domain, context_initial]
# =========================================================

def func1_context_initial(domain: str, decision_tree_rows: List[Dict[str, Any]]) -> List[List[Any]]:
    domain = domain.upper().strip()
    objectives: List[str] = []
    seen = set()

    for r in decision_tree_rows:
        if str(r.get("Type", "")).lower() != "decision_tree":
            continue
        if str(r.get("Domain", "")).upper().strip() != domain:
            continue
        try:
            score = int(r.get("Score"))
        except Exception:
            continue
        if score != 1:
            continue
        q = str(r.get("Question", "")).strip().upper()
        if not re.fullmatch(r"Q[1-6]", q):
            continue

        obj = norm_space(r.get("Objective", ""))
        if obj and obj not in seen:
            seen.add(obj)
            objectives.append(obj)

    context_initial = ", ".join(objectives)
    return [[domain, context_initial]]


# =========================================================
# Function 2
# - Evaluation_Initial from decision_tree rows
# - Filter Question == Q1
# - For each Score 0..5 return [Domain, Score, Action_Code, Text]
# =========================================================

def func2_evaluation_initial(domain: str, decision_tree_rows: List[Dict[str, Any]]) -> List[List[Any]]:
    domain = domain.upper().strip()
    out: List[List[Any]] = []

    for r in decision_tree_rows:
        if str(r.get("Type", "")).lower() != "decision_tree":
            continue
        if str(r.get("Domain", "")).upper().strip() != domain:
            continue
        q = str(r.get("Question", "")).strip().upper()
        if q != "Q1":
            continue

        try:
            score = int(r.get("Score"))
        except Exception:
            continue
        if score < 0 or score > 5:
            continue

        action_code = norm_space(r.get("Action_Code", ""))
        txt = (r.get("Text") or "").strip()
        out.append([domain, score, action_code, txt])

    out.sort(key=lambda x: x[1])
    return out


# =========================================================
# Function 3
# - Details_Initial from action_catalog rows
# - Return [Domain, Action_Code, Action_Title, Procedure, Text]
# =========================================================

def func3_details_initial(domain: str, action_catalog_rows: List[Dict[str, Any]]) -> List[List[Any]]:
    domain = domain.upper().strip()
    out: List[List[Any]] = []

    for r in action_catalog_rows:
        if str(r.get("Type", "")).lower() != "action_catalog":
            continue
        if str(r.get("Domain", "")).upper().strip() != domain:
            continue

        action_code = norm_space(r.get("Action_Code", ""))
        action_title = norm_space(r.get("Action_Title", ""))
        try:
            proc = int(r.get("Procedure"))
        except Exception:
            continue
        txt = (r.get("Text") or "").strip()
        out.append([domain, action_code, action_title, proc, txt])

    out.sort(key=lambda x: (x[1], x[3]))
    return out


# =========================================================
# Function 4
# - Join arrays from func1 + func2 + func3
# - Group by Domain + Action_Code (and keep Score from func2)
# - Return concatenated array as list[dict]
# =========================================================

def func4_join_arrays(
    domain: str,
    arr_context: List[List[Any]],
    arr_eval: List[List[Any]],
    arr_details: List[List[Any]],
) -> List[Dict[str, Any]]:
    domain = domain.upper().strip()

    # Context per domain
    context_initial = ""
    for row in arr_context:
        if len(row) >= 2 and str(row[0]).upper().strip() == domain:
            context_initial = row[1] or ""
            break

    # Details grouped by action_code
    details_by_action: Dict[str, Dict[str, Any]] = {}
    for d in arr_details:
        if len(d) < 5:
            continue
        _, action_code, action_title, proc, txt = d
        action_code = norm_space(action_code)
        if not action_code:
            continue

        bucket = details_by_action.setdefault(action_code, {
            "Action_Title": action_title or "",
            "procedures": []
        })
        if action_title and not bucket.get("Action_Title"):
            bucket["Action_Title"] = action_title

        bucket["procedures"].append({
            "procedure": proc,
            "text": txt or ""
        })

    # Eval becomes the driving grain (domain, score, action_code)
    joined: List[Dict[str, Any]] = []
    for e in arr_eval:
        if len(e) < 4:
            continue
        _, score, action_code, eval_txt = e
        action_code = norm_space(action_code)
        if not action_code:
            continue

        det = details_by_action.get(action_code, {})
        action_title = det.get("Action_Title", "")
        procs = det.get("procedures", []) or []
        procs = sorted(procs, key=lambda x: int(x.get("procedure", 999)))

        # Build Details_Initial as a single report ready block, preserving procedure order
        details_initial_parts = []
        for p in procs:
            pn = p.get("procedure")
            pt = (p.get("text") or "").strip()
            if not pt:
                continue
            details_initial_parts.append(f"Procedure {pn}\n{pt}")

        details_initial = "\n\n".join(details_initial_parts).strip()

        joined.append({
            "Domain": domain,
            "Score": score,
            "Action_Code": action_code,
            "Action_Title": action_title,
            "Context_Initial": context_initial,
            "Evaluation_Initial": (eval_txt or "").strip(),
            "Details_Initial": details_initial,
            "Procedures": procs,
        })

    joined.sort(key=lambda x: (x["Domain"], int(x["Score"]), x["Action_Code"]))
    return joined


# =========================================================
# Function 5
# - Improve text via OpenAI
# - Batch per domain, cache, parallel
# - Replace *_Initial with context, evaluation, details
# =========================================================

IMPROVE_SYSTEM = (
    "You are an expert data governance auditor and report writer. "
    "Write in formal audit tone, precise, concise, and report ready. "
    "English only. "
    "Return ONLY a strict JSON object with exactly these keys: "
    "context, evaluation, details. "
    "No extra keys. No markdown. No commentary."
)

def build_improve_prompt(item: Dict[str, Any]) -> str:
    domain = item.get("Domain", "")
    score = item.get("Score", "")
    action_code = item.get("Action_Code", "")
    action_title = item.get("Action_Title", "")

    context_initial = (item.get("Context_Initial") or "").strip()
    eval_initial = (item.get("Evaluation_Initial") or "").strip()
    details_initial = (item.get("Details_Initial") or "").strip()

    return f"""
You are improving text for a maturity assessment report.

Metadata
Domain: {domain}
Maturity score: {score}
Action code: {action_code}
Action title: {action_title}

Rewrite the following three fields for report use.

Rules
1. English only.
2. Formal audit tone, factual and prescriptive.
3. Output must be a single JSON object with exactly keys: context, evaluation, details.
4. context must be exactly 3 paragraphs.
5. evaluation must be exactly 4 paragraphs.
6. details must be exactly 4 paragraphs.
7. Do not use bullet lists.
8. Do not mention that you are rewriting or improving.
9. Avoid repetition across sections.

Input fields
Context_Initial
{context_initial}

Evaluation_Initial
{eval_initial}

Details_Initial
{details_initial}
""".strip()

def openai_client() -> OpenAI:
    load_dotenv(BASE_DIR / ".env")
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def load_improve_cache(cache_path: Path) -> Dict[str, Any]:
    return load_json(cache_path, default={"_meta": {}, "generated": {}})

def save_improve_cache(cache_path: Path, cache: Dict[str, Any]) -> None:
    cache.setdefault("_meta", {})["updated_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    save_json(cache_path, cache)

def item_fingerprint(item: Dict[str, Any]) -> str:
    """
    Fingerprint based on the actual inputs that affect generation.
    If any Initial field changes, we regenerate.
    """
    parts = [
        str(item.get("Domain", "")),
        str(item.get("Score", "")),
        str(item.get("Action_Code", "")),
        str(item.get("Action_Title", "")),
        str(item.get("Context_Initial", "")),
        str(item.get("Evaluation_Initial", "")),
        str(item.get("Details_Initial", "")),
    ]
    return sha256_text("\n".join(parts))

def should_improve(item: Dict[str, Any]) -> bool:
    # If already improved in file reuse path, still controlled by cache
    return True

def improve_items_with_cache(
    client: OpenAI,
    model: str,
    items: List[Dict[str, Any]],
    cache_path: Path,
    max_workers: int,
    batch_size: int,
    clear_cache: bool,
) -> List[Dict[str, Any]]:
    ensure_dir(cache_path.parent)

    cache = load_improve_cache(cache_path)
    generated = cache.setdefault("generated", {})

    if clear_cache:
        generated.clear()

    # Apply cached improvements if fingerprint matches
    to_do: List[Dict[str, Any]] = []
    for it in items:
        fp = item_fingerprint(it)
        cached = generated.get(fp)
        if cached and isinstance(cached, dict) and cached.get("context") and cached.get("evaluation") and cached.get("details"):
            it["context"] = cached["context"]
            it["evaluation"] = cached["evaluation"]
            it["details"] = cached["details"]
            it["_improve_cache_hit"] = True
        else:
            it["_improve_cache_hit"] = False
            to_do.append(it)

    log(f"Improve: total={len(items)} cache_hit={len(items)-len(to_do)} to_call={len(to_do)}")

    def worker(it: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        fp = item_fingerprint(it)
        prompt = build_improve_prompt(it)
        resp = client.chat.completions.create(
            model=model,
            temperature=0,
            messages=[
                {"role": "system", "content": IMPROVE_SYSTEM},
                {"role": "user", "content": prompt},
            ],
        )
        txt = (resp.choices[0].message.content or "").strip()
        obj = extract_first_json_object(txt)
        if not obj:
            raise ValueError("Model did not return valid JSON object")

        # Hard enforce keys
        context = (obj.get("context") or "").strip()
        evaluation = (obj.get("evaluation") or "").strip()
        details = (obj.get("details") or "").strip()

        if not context or not evaluation or not details:
            raise ValueError("Missing required JSON keys or empty content")

        return fp, {"context": context, "evaluation": evaluation, "details": details}

    if not to_do:
        return items

    # Batch + parallel
    batches = [to_do[i:i + batch_size] for i in range(0, len(to_do), batch_size)]
    done = 0
    total = len(to_do)

    for bi, batch in enumerate(batches, start=1):
        log(f"Improve batch {bi}/{len(batches)} size={len(batch)}")
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futs = {ex.submit(worker, it): it for it in batch}
            for fut in as_completed(futs):
                it = futs[fut]
                fp = item_fingerprint(it)
                try:
                    fp2, payload = fut.result()
                    it["context"] = payload["context"]
                    it["evaluation"] = payload["evaluation"]
                    it["details"] = payload["details"]
                    it["_improve_cache_hit"] = False
                    generated[fp2] = payload
                except Exception as e:
                    it["context"] = ""
                    it["evaluation"] = ""
                    it["details"] = ""
                    it["_improve_error"] = str(e)
                    generated[fp] = {"context": "", "evaluation": "", "details": "", "error": str(e)}

                done += 1
                if total:
                    pct = int((done / total) * 100)
                    print(f"\r[{now_ts()}] Improve progress {done}/{total} {pct}%   ", end="", flush=True)

        save_improve_cache(cache_path, cache)
        print("", flush=True)

    save_improve_cache(cache_path, cache)
    return items


# =========================================================
# Orchestrator for one domain input json
# =========================================================

def run_domain(domain: str, model: str, max_workers: int, batch_size: int, clear_cache: bool) -> Dict[str, Any]:
    domain = domain.upper().strip()
    in_path, out_path, cache_path = domain_io_paths(domain)

    if not in_path.exists():
        raise FileNotFoundError(f"Input not found: {in_path}")

    src = load_json(in_path, default={})
    decision_tree_rows = src.get("decision_tree") or []
    action_catalog_rows = src.get("action_catalog") or []
    meta = src.get("meta") or {}

    # Function 1
    arr_context = func1_context_initial(domain, decision_tree_rows)

    # Function 2
    arr_eval = func2_evaluation_initial(domain, decision_tree_rows)

    # Function 3
    arr_details = func3_details_initial(domain, action_catalog_rows)

    # Function 4
    joined = func4_join_arrays(domain, arr_context, arr_eval, arr_details)

    # Function 5
    client = openai_client()
    joined = improve_items_with_cache(
        client=client,
        model=model,
        items=joined,
        cache_path=cache_path,
        max_workers=max_workers,
        batch_size=batch_size,
        clear_cache=clear_cache,
    )

    # Build final output
    # Replace *_Initial with final fields
    out_items: List[Dict[str, Any]] = []
    for it in joined:
        out_items.append({
            "Domain": it.get("Domain"),
            "Score": it.get("Score"),
            "Action_Code": it.get("Action_Code"),
            "Action_Title": it.get("Action_Title"),
            "context": it.get("context", ""),
            "evaluation": it.get("evaluation", ""),
            "details": it.get("details", ""),
            # Optional trace
            "Procedures": it.get("Procedures", []),
            "_cache_hit": bool(it.get("_improve_cache_hit", False)),
            "_error": it.get("_improve_error", ""),
        })

    out_obj = {
        "items": out_items,
        "meta": {
            "domain": domain,
            "input_file": str(in_path),
            "output_file": str(out_path),
            "model": model,
            "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "source_meta": meta,
            "counts": {
                "context_rows": len(arr_context),
                "evaluation_rows": len(arr_eval),
                "details_rows": len(arr_details),
                "joined_rows": len(joined),
            },
        },
    }

    save_json(out_path, out_obj)
    log(f"Saved improved output: {out_path}")
    log(f"Saved improve cache:  {cache_path}")
    return out_obj


# =========================================================
# Main
# =========================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="DOMMx Theory Improve (report ready rewrite)")

    parser.add_argument("--mode", choices=["all", "domain"], default="all",
                        help="all reads domains from flow.yaml, domain runs only one acronym")
    parser.add_argument("--domain", default=None, help="domain acronym like DG, DQ, AIML, required when mode=domain")
    parser.add_argument("--model", default=DEFAULT_MODEL_IMPROVE, help="OpenAI model for improvements")
    parser.add_argument("--max-workers", type=int, default=DEFAULT_MAX_WORKERS, help="parallel workers")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="batch size for parallel requests")
    parser.add_argument("--clear-cache", action="store_true", help="clear improve cache for target domains")

    args = parser.parse_args()

    ensure_dir(OUTPUT_DIR)
    ensure_dir(CACHE_DIR)

    if args.mode == "domain":
        if not args.domain:
            raise ValueError("mode=domain requires --domain")
        domains = [args.domain.upper().strip()]
    else:
        flow = load_yaml(FLOW_PATH)
        flow_items = get_flow_domains(flow)
        domains = [str(d.get("acronym", "")).upper().strip() for d in flow_items if d.get("acronym")]

    log(f"Mode={args.mode} domains={domains}")
    log(f"Model={args.model} max_workers={args.max_workers} batch_size={args.batch_size}")
    log(f"Input dir={OUTPUT_DIR}")
    log(f"Cache dir={CACHE_DIR}")

    for i, dom in enumerate(domains, start=1):
        log(f"Running {i}/{len(domains)} domain {dom}")
        run_domain(
            domain=dom,
            model=args.model,
            max_workers=args.max_workers,
            batch_size=args.batch_size,
            clear_cache=args.clear_cache,
        )

    log("Done")

if __name__ == "__main__":
    main()