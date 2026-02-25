import json
import os
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml
import xml.etree.ElementTree as ET


# =========================================================
# PATH HELPERS
# =========================================================

def _project_dir(base_dir: str, project_id: str) -> Path:
    return Path(base_dir) / "data" / "projects" / str(project_id)


def _cache_dir(base_dir: str, project_id: str, scope: str, user_id: Optional[str] = None) -> Path:
    root = _project_dir(base_dir, project_id) / "cache" / "ai_reports"
    if scope == "global":
        return root / "global"
    return root / "users" / str(user_id)


def _domain_cache_path(base_dir: str, project_id: str, domain_code: str, scope: str, user_id: Optional[str]) -> Path:
    return _cache_dir(base_dir, project_id, scope, user_id) / f"domain_{domain_code}.json"


def _domain_md_path(base_dir: str, project_id: str, domain_code: str, scope: str, user_id: Optional[str]) -> Path:
    return _cache_dir(base_dir, project_id, scope, user_id) / f"domain_{domain_code}.md"


def _domain_xml_path(base_dir: str, project_id: str, domain_code: str, scope: str, user_id: Optional[str]) -> Path:
    return _cache_dir(base_dir, project_id, scope, user_id) / f"domain_{domain_code}.xml"


# =========================================================
# YAML LOADING
# =========================================================

def load_yaml_file(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_domain_yamls(domains_root: str, domain_code: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    dt_path = Path(domains_root) / f"{domain_code}_decision_tree.yaml"
    ac_path = Path(domains_root) / f"{domain_code}_action_catalog.yaml"
    return load_yaml_file(str(dt_path)), load_yaml_file(str(ac_path))


# =========================================================
# AVERAGE + LEVEL + DOMAIN ACTION
# =========================================================

def compute_domain_avg(scores: Dict[str, int]) -> float:
    if not scores:
        return 0.0
    return round(sum(scores.values()) / float(len(scores)), 2)


def avg_to_level(avg: float) -> int:
    lvl = int(round(avg))
    return max(0, min(5, lvl))


def resolve_domain_action_code(decision_tree: Dict[str, Any], level: int) -> Optional[str]:
    questions = decision_tree.get("questions")
    if isinstance(questions, dict):
        first_q = next(iter(questions.values()))
    elif isinstance(questions, list) and questions:
        first_q = questions[0]
    else:
        return None

    scores = first_q.get("scores") or first_q.get("scale") or {}
    entry = scores.get(str(level)) or scores.get(level)
    if isinstance(entry, dict):
        return entry.get("action_code")
    return None


# =========================================================
# REPORT BUILD
# =========================================================

def build_domain_report(
    domain_code: str,
    decision_tree: Dict[str, Any],
    action_catalog: Dict[str, Any],
    domain_scores: Dict[str, int],
    domain_comments: Dict[str, str],
) -> Dict[str, Any]:

    avg = compute_domain_avg(domain_scores)
    level = avg_to_level(avg)
    domain_action = resolve_domain_action_code(decision_tree, level)

    action_block = action_catalog.get(domain_action, {})

    questions_out = []
    questions = decision_tree.get("questions", {})

    for qid, qdata in questions.items():
        score = domain_scores.get(qid)
        if score is None:
            continue

        questions_out.append({
            "question_id": qid,
            "text": qdata.get("text"),
            "objective": qdata.get("objective"),
            "score": score,
            "action_code": domain_action,
            "action_title": action_block.get("title"),
            "procedure": action_block.get("procedure"),
            "recommendations": action_block.get("recommendations"),
            "notes": action_block.get("notes"),
            "references": action_block.get("references"),
            "comment": domain_comments.get(qid),
        })

    return {
        "generated_at": datetime.utcnow().isoformat(),
        "domain": decision_tree.get("domain", {}),
        "avg_score": avg,
        "domain_level": level,
        "domain_action_code": domain_action,
        "questions": questions_out,
    }


# =========================================================
# CROSS REFERENCES (NORMALIZED + CLASSIFIED)
# =========================================================

def _normalize_reference(ref: str) -> str:
    s = (ref or "").strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\b(chapter|chap\.?|cap[ií]tulo|cap\.?)\b", "ch", s, flags=re.IGNORECASE)
    s = re.sub(r"\b(section|sec\.?)\b", "sec", s, flags=re.IGNORECASE)
    s = re.sub(r"\b(dmbok 2|dmbok2|dmbok)\b", "dmbok2", s, flags=re.IGNORECASE)
    return s.strip(" .;,")


def _classify_reference(norm: str) -> str:
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
    if "zenodo" in s or "dommx" in s or "slr" in s:
        return "SLR_DOMMx"
    return "OTHER"


def extract_domain_cross_references(decision_tree: Dict[str, Any], action_catalog: Dict[str, Any]) -> Dict[str, Any]:

    seen: Set[str] = set()
    ordered = []
    ordered_norm = []
    by_type = {}
    by_type_norm = {}

    def _add(ref):
        if not ref:
            return
        orig = str(ref).strip()
        norm = _normalize_reference(orig)
        if norm in seen:
            return
        seen.add(norm)
        ordered.append(orig)
        ordered_norm.append(norm)

        cat = _classify_reference(norm)
        by_type.setdefault(cat, []).append(orig)
        by_type_norm.setdefault(cat, []).append(norm)

    def _extract_tail(text):
        if not text:
            return None
        m = re.search(r"\(([^()]*)\)\s*$", str(text).strip())
        return m.group(1).strip() if m else None

    # decision_tree scan
    def _walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if str(k).lower() in ("cross_reference", "references"):
                    if isinstance(v, list):
                        for x in v:
                            _add(x)
                    else:
                        _add(v)
                _walk(v)
        elif isinstance(obj, list):
            for x in obj:
                _walk(x)

    _walk(decision_tree)

    # action catalog
    for _, a in action_catalog.items():
        if not isinstance(a, dict):
            continue
        _add(a.get("references"))
        _add(_extract_tail(a.get("recommendations")))
        _add(_extract_tail(a.get("notes")))

    return {
        "references": ordered,
        "references_normalized": ordered_norm,
        "by_type": by_type,
        "by_type_normalized": by_type_norm,
    }


# =========================================================
# PROMPT FORMATTER
# =========================================================

def format_references_for_prompt(refs: Dict[str, Any], max_per_type: int = 5) -> str:
    lines = []
    by_type = refs.get("by_type", {})

    for t, items in by_type.items():
        lines.append(f"{t}:")
        for ref in items[:max_per_type]:
            lines.append(f"- {ref}")
        lines.append("")

    return "\n".join(lines).strip()