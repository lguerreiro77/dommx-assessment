import json
import os
import math
import re
import time
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Callable

import yaml
import xml.etree.ElementTree as ET

try:
    from docx import Document
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
except Exception:
    Document = None  # type: ignore


# =========================================================
# CONFIG
# =========================================================

REPORT_ENGINE_VERSION = "1.0.0"
DEFAULT_AI_TIMEOUT_SEC = 60
DEFAULT_AI_RETRIES = 3
DEFAULT_AI_PARALLEL_WORKERS = 6


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


def _manifest_path(base_dir: str, project_id: str, scope: str, user_id: Optional[str]) -> Path:
    return _cache_dir(base_dir, project_id, scope, user_id) / "report_manifest.json"


def _report_docx_path(base_dir: str, project_id: str, scope: str, user_id: Optional[str]) -> Path:
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    if scope == "global":
        return _cache_dir(base_dir, project_id, scope, user_id) / f"DOMMx_Report_{project_id}_{stamp}.docx"
    return _cache_dir(base_dir, project_id, scope, user_id) / f"DOMMx_Report_{project_id}_{user_id}_{stamp}.docx"


# =========================================================
# YAML LOADING
# =========================================================

def load_yaml_file(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# =========================================================
# AVERAGE + LEVEL
# =========================================================

def compute_domain_avg(scores: Dict[str, int]) -> float:
    if not scores:
        return 0.0
    return round(sum(scores.values()) / float(len(scores)), 2)


def avg_to_level(avg: float) -> int:
    # Auditoria: conservador (floor), não arredonda pra cima
    lvl = int(math.floor(avg))
    return max(0, min(5, lvl))


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


def extract_domain_cross_references(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Cross references vêm principalmente dos JSONs theory_cluster_output
    Cada entry tem campo Cross_Reference (lista ou string)
    """
    seen: Set[str] = set()
    ordered: List[str] = []
    ordered_norm: List[str] = []
    by_type: Dict[str, List[str]] = {}
    by_type_norm: Dict[str, List[str]] = {}

    def _add(ref: Any) -> None:
        if not ref:
            return
        if isinstance(ref, list):
            for x in ref:
                _add(x)
            return
        orig = str(ref).strip()
        if not orig:
            return
        norm = _normalize_reference(orig)
        if norm in seen:
            return
        seen.add(norm)
        ordered.append(orig)
        ordered_norm.append(norm)
        cat = _classify_reference(norm)
        by_type.setdefault(cat, []).append(orig)
        by_type_norm.setdefault(cat, []).append(norm)

    for e in entries:
        _add(e.get("Cross_Reference"))

    return {
        "references": ordered,
        "references_normalized": ordered_norm,
        "by_type": by_type,
        "by_type_normalized": by_type_norm,
    }


def format_references_for_prompt(refs: Dict[str, Any], max_per_type: int = 5) -> str:
    lines = []
    by_type = refs.get("by_type", {})
    for t, items in by_type.items():
        lines.append(f"{t}:")
        for ref in items[:max_per_type]:
            lines.append(f"- {ref}")
        lines.append("")
    return "\n".join(lines).strip()


# =========================================================
# DOCX HELPERS
# =========================================================

def _docx_add_toc(doc: "Document") -> None:
    """
    Insere um campo TOC. O Word atualiza ao abrir (ou F9)
    """
    p = doc.add_paragraph()
    r = p.add_run()
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), r'TOC \\o "1-3" \\h \\z \\u')
    r._r.addnext(fld)


def _docx_add_kv_table(doc: "Document", rows: List[Tuple[str, str]]) -> None:
    table = doc.add_table(rows=len(rows), cols=2)
    for i, (k, v) in enumerate(rows):
        table.cell(i, 0).text = str(k)
        table.cell(i, 1).text = str(v)


def _docx_add_score_table(doc: "Document", domain_rows: List[Dict[str, Any]]) -> None:
    table = doc.add_table(rows=1 + len(domain_rows), cols=5)
    hdr = table.rows[0].cells
    hdr[0].text = "Sequência"
    hdr[1].text = "Domínio"
    hdr[2].text = "Nome"
    hdr[3].text = "Média"
    hdr[4].text = "Nível (floor)"

    for i, r in enumerate(domain_rows, start=1):
        row = table.rows[i].cells
        row[0].text = str(r.get("sequence", ""))
        row[1].text = str(r.get("acronym", ""))
        row[2].text = str(r.get("name", ""))
        row[3].text = f'{r.get("avg", 0):.2f}'
        row[4].text = str(r.get("level", 0))


def _sha256_bytes(b: bytes) -> str:
    h = hashlib.sha256()
    h.update(b)
    return h.hexdigest()


def _stable_json_hash(obj: Any) -> str:
    b = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _sha256_bytes(b)


# =========================================================
# COMMENTS PARSER
# =========================================================

def _parse_comment_xml(xml_text: str) -> Dict[str, Any]:
    """
    Espera algo como:
    <Comment>
      <Domain>DG</Domain>
      <Question>Q1</Question>
      <MaturityScore>2</MaturityScore>
      <Text>...</Text>
    </Comment>
    """
    out: Dict[str, Any] = {}
    if not xml_text:
        return out
    try:
        root = ET.fromstring(xml_text)
        for tag in ("Domain", "Question", "MaturityScore", "Text"):
            node = root.find(tag)
            if node is not None and node.text is not None:
                out[tag] = node.text.strip()
    except Exception:
        return out
    return out


# =========================================================
# SERVICE
# =========================================================

class AIReportService:
    """
    Gera relatório Word (.docx) nível auditoria para:
    user scope: (user_id + project_id)
    admin scope: (project_id) agregando usuários
    IA é opcional e deve ser mínima, usa JSONs e caches antes de chamar IA
    """

    def __init__(
        self,
        base_dir: str,
        repo: Any,
        ai_call: Optional[Callable[[List[Dict[str, str]]], str]] = None,
        ai_timeout_sec: int = DEFAULT_AI_TIMEOUT_SEC,
        ai_retries: int = DEFAULT_AI_RETRIES,
        ai_workers: int = DEFAULT_AI_PARALLEL_WORKERS,
    ):
        self.base_dir = str(base_dir)
        self.repo = repo
        self.ai_call = ai_call
        self.ai_timeout_sec = ai_timeout_sec
        self.ai_retries = ai_retries
        self.ai_workers = ai_workers

    # ----------------------------
    # PUBLIC API
    # ----------------------------

    def generate_report_docx(
        self,
        project_id: str,
        user_id: Optional[str] = None,
        is_admin: bool = False,
        language: str = "en",
        force_regen: bool = False,
    ) -> str:
        """
        Returns the path of the generated .docx (project cache).

        Policy:
        - The report model is built deterministically in ENGLISH.
        - If language != 'en', the full report JSON is translated in ONE call (cached).
        - DOCX is rendered from the final JSON. The DOCX builder never calls AI.
        """
        if Document is None:
            raise RuntimeError("python-docx not available in the environment.")

        scope = "global" if is_admin else "user"
        cache_root = _cache_dir(self.base_dir, project_id, scope, user_id)
        cache_root.mkdir(parents=True, exist_ok=True)

        # 1) Flow ordering
        flow = self._load_flow()
        domain_flow = sorted(flow.get("Domain_flow", []), key=lambda d: d.get("sequence", 999))

        # 2) Results
        results_rows = self._load_results(project_id, user_id, is_admin=is_admin)
        answers_map = self._extract_answers(results_rows)  # domain_key -> {Q1:score,...}

        # 3) Comments
        comments_rows = self._load_comments(project_id, user_id, is_admin=is_admin)
        comments_map = self._build_comments_map(comments_rows)  # acronym -> qid -> list[comment]

        # 4) Metrics
        domain_metrics = self._compute_domain_metrics(domain_flow, answers_map)

        # 5) Dependencies + domain theory
        dep_json = self._load_dependencies_json()
        domain_theory = self._load_all_domain_theory_json(domain_flow)

        # 6) Deterministic report model (always EN)
        model = self._build_report_model(
            project_id=project_id,
            user_id=user_id,
            is_admin=is_admin,
            language="en",
            domain_flow=domain_flow,
            answers_map=answers_map,
            comments_map=comments_map,
            domain_metrics=domain_metrics,
            dep_json=dep_json,
            domain_theory=domain_theory,
        )
        model_hash = _stable_json_hash(model)

        # 7) Full report JSON (EN) + AI enrichment (A only)
        report_json = self._build_report_json_from_model(model)
        report_json = self._enrich_report_json_with_ai(report_json, model_hash=model_hash, force_regen=force_regen)

        # 8) Translate full JSON if needed (single call)
        target_lang = (language or "en").strip().lower()
        if target_lang != "en":
            report_json = self._translate_full_report_json(
                report_json,
                model_hash=model_hash,
                target_language=target_lang,
                force_regen=force_regen,
            )

        # 9) Render DOCX from JSON
        docx_path = _report_docx_path(self.base_dir, project_id, scope, user_id)
        self._render_docx_from_report_json(docx_path, report_json)

        # 10) Manifest
        with open(docx_path, "rb") as f:
            doc_bytes = f.read()

        manifest = {
            "report_engine_version": REPORT_ENGINE_VERSION,
            "generated_at": datetime.utcnow().isoformat(),
            "scope": scope,
            "project_id": str(project_id),
            "user_id": str(user_id) if user_id else None,
            "model_hash_sha256": model_hash,
            "docx_sha256": _sha256_bytes(doc_bytes),
            "docx_path": str(docx_path),
            "language": target_lang,
            "inputs": {
                "flow_yaml": str(Path(self.base_dir) / "data" / "general" / "flow.yaml"),
                "dependencies_json": str(Path(self.base_dir) / "data" / "global" / "theory" / "Dependencies_inconsistencies_theory_cluster_output.json"),
                "domain_theory_dir": str(Path(self.base_dir) / "data" / "global" / "theory"),
            },
        }
        mpath = _manifest_path(self.base_dir, project_id, scope, user_id)
        with open(mpath, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        return str(docx_path)

    def generate_report_package(
        self,
        project_id: str,
        user_id: Optional[str] = None,
        is_admin: bool = False,
        language: str = "en",
        force_regen: bool = False,
    ) -> str:
        """Generates a ZIP package containing DOCX + PDF (if available)."""
        docx_path = Path(self.generate_report_docx(
            project_id=project_id,
            user_id=user_id,
            is_admin=is_admin,
            language=language,
            force_regen=force_regen,
        ))
        pdf_path = self._try_convert_docx_to_pdf(docx_path)
        zip_path = self._build_zip_package(docx_path, pdf_path)
        return str(zip_path)
    def _load_flow(self) -> Dict[str, Any]:
        path = Path(self.base_dir) / "data" / "general" / "flow.yaml"
        return load_yaml_file(str(path))

    def _load_results(self, project_id: str, user_id: Optional[str], is_admin: bool) -> List[Dict[str, Any]]:
        rows = self.repo.fetch_all("results") or []
        if is_admin:
            return [r for r in rows if str(r.get("project_id")) == str(project_id)]
        return [r for r in rows if str(r.get("project_id")) == str(project_id) and str(r.get("user_id")) == str(user_id)]

    def _load_comments(self, project_id: str, user_id: Optional[str], is_admin: bool) -> List[Dict[str, Any]]:
        rows = self.repo.fetch_all("comments") or []
        if is_admin:
            return [r for r in rows if str(r.get("project_id")) == str(project_id)]
        return [r for r in rows if str(r.get("project_id")) == str(project_id) and str(r.get("user_id")) == str(user_id)]

    def _load_dependencies_json(self) -> Dict[str, Any]:
        path = Path(self.base_dir) / "data" / "global" / "theory" / "Dependencies_inconsistencies_theory_cluster_output.json"
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _load_all_domain_theory_json(self, domain_flow: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """
        Carrega <<ACRONYM>>_theory_cluster_output.json para todos os domínios do flow
        """
        out: Dict[str, Dict[str, Any]] = {}
        root = Path(self.base_dir) / "data" / "global" / "theory"
        for d in domain_flow:
            ac = d.get("acronym")
            if not ac:
                continue
            fpath = root / f"{ac}_theory_cluster_output.json"
            if not fpath.exists():
                continue
            with open(fpath, "r", encoding="utf-8") as f:
                out[str(ac)] = json.load(f)
        return out

    # ----------------------------
    # RESULTS + COMMENTS NORMALIZATION
    # ----------------------------

    def _extract_answers(self, results_rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
        """
        Returns:
          domain_key (domain_0 etc) -> {Q1:score, Q2:score}
        """
        answers_map: Dict[str, Dict[str, int]] = {}
        if not results_rows:
            return answers_map

        try:
            from auth.crypto_service import decrypt_text
        except Exception:
            decrypt_text = None  # type: ignore

        for r in results_rows:
            enc = r.get("answers_json_encrypted")
            if not enc or decrypt_text is None:
                continue
            try:
                payload = json.loads(decrypt_text(enc))
            except Exception:
                continue

            answers = payload.get("answers", payload)
            if not isinstance(answers, dict):
                continue

            for domain_key, qmap in answers.items():
                if not isinstance(qmap, dict):
                    continue
                dm = answers_map.setdefault(str(domain_key), {})
                for qid, score in qmap.items():
                    try:
                        dm[str(qid)] = int(score)
                    except Exception:
                        continue

        return answers_map

    def _build_comments_map(self, comments_rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
        """
        Returns:
          acronym -> qid -> [ {text, maturity_score, created_at}, ... ]
        """
        out: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        for r in comments_rows or []:
            xml_text = r.get("comment") or r.get("comment_xml") or ""
            parsed = _parse_comment_xml(xml_text)
            ac = parsed.get("Domain")
            qid = parsed.get("Question")
            if not ac or not qid:
                continue
            entry = {
                "text": parsed.get("Text"),
                "maturity_score": parsed.get("MaturityScore"),
                "created_at": r.get("created_at") or r.get("timestamp") or r.get("updated_at"),
            }
            out.setdefault(str(ac), {}).setdefault(str(qid), []).append(entry)
        return out

    # ----------------------------
    # METRICS
    # ----------------------------

    @staticmethod
    def _domain_id_to_key(domain_id: int) -> str:
        # flow domain_id começa em 1, results usa domain_0
        return f"domain_{int(domain_id) - 1}"

    def _compute_domain_metrics(self, domain_flow: List[Dict[str, Any]], answers_map: Dict[str, Dict[str, int]]) -> Dict[str, Dict[str, Any]]:
        """
        Returns:
          acronym -> {avg, level, count_questions, domain_id, sequence, name, dependence}
        """
        metrics: Dict[str, Dict[str, Any]] = {}
        for d in domain_flow:
            domain_id = d.get("domain_id")
            ac = d.get("acronym")
            if not domain_id or not ac:
                continue
            key = self._domain_id_to_key(int(domain_id))
            qmap = answers_map.get(key)
            if not qmap:
                continue
            avg = compute_domain_avg(qmap)
            level = avg_to_level(avg)
            metrics[str(ac)] = {
                "avg": avg,
                "level": level,
                "count_questions": len(qmap),
                "domain_id": int(domain_id),
                "sequence": d.get("sequence"),
                "name": d.get("name"),
                "dependence": d.get("dependence", []),
            }
        return metrics

    # ----------------------------
    # REPORT MODEL (DETERMINISTIC)
    # ----------------------------

    def _build_report_model(
        self,
        project_id: str,
        user_id: Optional[str],
        is_admin: bool,
        language: str,
        domain_flow: List[Dict[str, Any]],
        answers_map: Dict[str, Dict[str, int]],
        comments_map: Dict[str, Dict[str, List[Dict[str, Any]]]],
        domain_metrics: Dict[str, Dict[str, Any]],
        dep_json: Dict[str, Any],
        domain_theory: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:

        avgs = [v["avg"] for v in domain_metrics.values()]
        global_score = round(sum(avgs) / float(len(avgs)), 2) if avgs else 0.0
        global_level = avg_to_level(global_score)

        dep_index: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for item in dep_json.get("inconsistencies", []) or []:
            dep_index[(str(item.get("domain_acronym")), str(item.get("reference_acronym")))] = item

        domains_out: List[Dict[str, Any]] = []

        for d in domain_flow:
            ac = str(d.get("acronym"))
            if ac not in domain_metrics:
                continue

            m = domain_metrics[ac]
            domain_id = int(m["domain_id"])
            domain_key = self._domain_id_to_key(domain_id)
            qmap = answers_map.get(domain_key, {})

            theory_entries = (domain_theory.get(ac) or {}).get("decision_tree") or []
            join_lookup = {str(e.get("Join_Key")): e for e in theory_entries if isinstance(e, dict) and e.get("Join_Key")}

            questions_out: List[Dict[str, Any]] = []
            actions_out: List[Dict[str, Any]] = []

            for qid, score in qmap.items():
                join_key = f"{ac}|{qid}|{int(score)}"
                te = join_lookup.get(join_key, {})
                q_comments = comments_map.get(ac, {}).get(qid, [])
                questions_out.append({
                    "question_id": qid,
                    "score": int(score),
                    "join_key": join_key,
                    "theory": {
                        "text": te.get("Text"),
                        "explanation": te.get("Explanation"),
                        "objective": te.get("Objective"),
                        "action_code": te.get("Action_Code"),
                        "action_description": te.get("Action_Description"),
                        "cross_reference": te.get("Cross_Reference"),
                    },
                    "comments": q_comments,
                })
                if te.get("Action_Code"):
                    actions_out.append({
                        "action_code": te.get("Action_Code"),
                        "action_description": te.get("Action_Description"),
                        "trigger_join_key": join_key,
                        "question_id": qid,
                        "score": int(score),
                    })

            level_entries = [e for e in theory_entries if isinstance(e, dict) and int(e.get("Score", -1)) == int(m["level"])]

            deps_ids = d.get("dependence", []) or []
            deps_acronyms: List[str] = []
            for dep_id in deps_ids:
                try:
                    dep_id_int = int(dep_id)
                except Exception:
                    continue
                dep_ac = next((x.get("acronym") for x in domain_flow if int(x.get("domain_id", -1)) == dep_id_int), None)
                if dep_ac:
                    deps_acronyms.append(str(dep_ac))

            dep_analysis = []
            for ref_ac in deps_acronyms:
                ref_m = domain_metrics.get(ref_ac)
                scenario_key = None
                if not ref_m:
                    scenario_key = "reference_not_evaluated"
                    ref_level = None
                else:
                    ref_level = int(ref_m["level"])
                    if ref_level < int(m["level"]):
                        scenario_key = "reference_inferior"
                    elif ref_level > int(m["level"]):
                        scenario_key = "reference_superior"
                    else:
                        scenario_key = None

                dep_item = dep_index.get((ac, ref_ac))
                dep_analysis.append({
                    "primary_acronym": ac,
                    "reference_acronym": ref_ac,
                    "primary_level": int(m["level"]),
                    "reference_level": ref_level,
                    "scenario_key": scenario_key,
                    "json_item": dep_item,
                })

            refs = extract_domain_cross_references(theory_entries)

            domains_out.append({
                "sequence": d.get("sequence"),
                "domain_id": domain_id,
                "acronym": ac,
                "name": d.get("name"),
                "avg": float(m["avg"]),
                "level": int(m["level"]),
                "dependence_ids": deps_ids,
                "dependence_acronyms": deps_acronyms,
                "dependency_analysis": dep_analysis,
                "questions": questions_out,
                "actions": actions_out,
                "level_entries": level_entries,
                "cross_references": refs,
            })

        domains_out.sort(key=lambda x: x.get("sequence", 999))

        return {
            "meta": {
                "project_id": str(project_id),
                "user_id": str(user_id) if user_id else None,
                "scope": "global" if is_admin else "user",
                "language": language,
                "generated_at": datetime.utcnow().isoformat(),
                "report_engine_version": REPORT_ENGINE_VERSION,
            },
            "scores": {
                "global_avg": global_score,
                "global_level": global_level,
            },
            "domains": domains_out,
            "dependencies_meta": {
                "structural_severity_meaning": dep_json.get("Structural Severity Meaning"),
            }
        }

    # ----------------------------
    # IA + CACHE
    # ----------------------------

    def _build_narratives_with_cache(self, model: Dict[str, Any], model_hash: str, force_regen: bool) -> Dict[str, Any]:
        meta = model.get("meta", {})
        project_id = meta.get("project_id")
        scope = meta.get("scope")
        user_id = meta.get("user_id")

        assert project_id is not None

        narratives: Dict[str, Any] = {}

        overview_cache = _cache_dir(self.base_dir, project_id, scope, user_id) / "section_overview.json"
        narratives["overview"] = self._cached_section(
            cache_path=overview_cache,
            input_fingerprint={"model_hash": model_hash, "section": "overview"},
            force_regen=force_regen,
            builder=lambda: self._compose_overview_text(model),
            ai=True,
        )

        dep_cache = _cache_dir(self.base_dir, project_id, scope, user_id) / "section_dependencies.json"
        narratives["dependencies"] = self._cached_section(
            cache_path=dep_cache,
            input_fingerprint={"model_hash": model_hash, "section": "dependencies"},
            force_regen=force_regen,
            builder=lambda: self._compose_dependencies_text(model),
            ai=True,
        )

        domain_results: Dict[str, Any] = {}
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _task(dom: Dict[str, Any]) -> Tuple[str, Any]:
            ac = dom["acronym"]
            cpath = _domain_cache_path(self.base_dir, project_id, ac, scope, user_id)
            out = self._cached_section(
                cache_path=cpath,
                input_fingerprint={"model_hash": model_hash, "section": f"domain:{ac}"},
                force_regen=force_regen,
                builder=lambda: self._compose_domain_text(dom),
                ai=True,
            )
            return ac, out

        with ThreadPoolExecutor(max_workers=self.ai_workers) as ex:
            futures = [ex.submit(_task, d) for d in model.get("domains", [])]
            for f in as_completed(futures):
                ac, out = f.result()
                domain_results[ac] = out

        narratives["domains"] = domain_results

        concl_cache = _cache_dir(self.base_dir, project_id, scope, user_id) / "section_conclusion.json"
        narratives["conclusion"] = self._cached_section(
            cache_path=concl_cache,
            input_fingerprint={"model_hash": model_hash, "section": "conclusion"},
            force_regen=force_regen,
            builder=lambda: self._compose_conclusion_text(model),
            ai=True,
        )

        return narratives

    def _cached_section(
        self,
        cache_path: Path,
        input_fingerprint: Dict[str, Any],
        builder: Callable[[], str],
        force_regen: bool,
        ai: bool,
    ) -> Dict[str, Any]:
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        if not force_regen and cache_path.exists():
            try:
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
                if cached.get("input_fingerprint") == input_fingerprint and cached.get("text"):
                    return cached
            except Exception:
                pass

        base_text = builder()

        if ai and self.ai_call:
            final_text = self._ai_polish(
                section_id=str(input_fingerprint.get("section")),
                base_text=base_text,
            )
        else:
            final_text = base_text

        out = {
            "input_fingerprint": input_fingerprint,
            "text": final_text,
            "generated_at": datetime.utcnow().isoformat(),
        }
        cache_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        return out

    def _ai_polish(self, section_id: str, base_text: str) -> str:
        prompt = (
            "Você é um redator técnico de auditoria. Reescreva mantendo fidelidade total.\n"
            "Regras:\n"
            "- NÃO invente fatos, números, scores, nomes\n"
            "- NÃO altere níveis ou médias\n"
            "- NÃO inclua novas recomendações não suportadas pelo texto base\n"
            "- Produza texto em português PT-BR, objetivo, sem floreios\n"
            "- Use parágrafos curtos e listas quando fizer sentido\n\n"
            f"SEÇÃO: {section_id}\n"
            "TEXTO BASE:\n"
            f"{base_text}\n"
        )

        messages = [
            {"role": "system", "content": "Return only the final rewritten text. No JSON. No explanations."},
            {"role": "user", "content": prompt},
        ]

        last_err = None
        for attempt in range(1, self.ai_retries + 1):
            try:
                return self._call_ai_with_timeout(messages)
            except Exception as e:
                last_err = e
                time.sleep(0.4 * attempt)
        return base_text

    def _call_ai_with_timeout(self, messages: List[Dict[str, str]]) -> str:
        if not self.ai_call:
            raise RuntimeError("ai_call not configured")
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(self.ai_call, messages)
            return fut.result(timeout=self.ai_timeout_sec)

    # ----------------------------
    # DETERMINISTIC TEXT BUILDERS
    # ----------------------------

    def _compose_overview_text(self, model: Dict[str, Any]) -> str:
        scores = model.get("scores", {})
        doms = model.get("domains", [])
        lines: List[str] = []
        lines.append(f"Score global (média dos domínios avaliados): {scores.get('global_avg', 0):.2f}.")
        lines.append(f"Nível global (floor): {scores.get('global_level', 0)}.")
        lines.append("")
        lines.append("A sequência dos domínios segue a estrutura consolidada a partir de DAMA-DMBOK2, DCAM e frameworks amplamente adotados no mercado.,")
        lines.append("que define a ordem estrutural de análise e as dependências entre domínios.")
        lines.append("")
        lines.append("Domínios avaliados:")
        for d in doms:
            lines.append(f"- {d['sequence']}. {d['acronym']} ({d['name']}): média {d['avg']:.2f}, nível {d['level']}.")
        return "\n".join(lines).strip()

    def _compose_dependencies_text(self, model: Dict[str, Any]) -> str:
        lines: List[str] = []
        lines.append("Análise de coerência estrutural e dependências entre domínios.")
        meaning = model.get("dependencies_meta", {}).get("structural_severity_meaning")
        if meaning:
            lines.append("")
            lines.append("Classificação de severidade estrutural (referência):")
            if isinstance(meaning, dict):
                for k, v in meaning.items():
                    lines.append(f"- {k}: {v}")
            else:
                lines.append(str(meaning))

        lines.append("")
        for dom in model.get("domains", []):
            deps = ", ".join(dom.get("dependence_acronyms", [])) or "nenhuma"
            lines.append(f"[{dom['acronym']}] Dependências (ordem do flow.yaml): {deps}")
            for da in dom.get("dependency_analysis", []):
                if not da.get("scenario_key"):
                    continue
                item = da.get("json_item") or {}
                scenario_key = da.get("scenario_key")
                scenario = (item.get("scenarios") or {}).get(scenario_key) if item else None
                if not scenario:
                    lines.append(f"- {dom['acronym']} vs {da.get('reference_acronym')}: desalinhamento detectado (sem texto de cenário no JSON).")
                    continue
                sev = item.get("Structural Severity Classification", {})
                sev_txt = ""
                if isinstance(sev, dict):
                    sev_txt = sev.get("classification", "") or sev.get("level", "") or ""
                comp = scenario.get("comparison")
                analysis_text = scenario.get("analysis_text") or scenario.get("whynot_text") or ""
                lines.append(f"- {dom['acronym']} → {da.get('reference_acronym')}: {comp} | Severidade: {sev_txt}".strip())
                if analysis_text:
                    lines.append(f"  {analysis_text}".strip())
            lines.append("")
        return "\n".join(lines).strip()

    def _compose_domain_text(self, dom: Dict[str, Any]) -> str:
        ac = dom["acronym"]
        avg = dom["avg"]
        level = dom["level"]
        name = dom["name"]

        lines: List[str] = []
        lines.append(f"Domínio {ac} | {name}")
        lines.append(f"Média: {avg:.2f} | Nível (floor): {level}")
        lines.append("")

        entries = dom.get("level_entries", []) or []
        if entries:
            lines.append("Interpretação do estágio atual (base teórica do nível atingido):")
            seen: Set[str] = set()
            for e in entries:
                t = (e.get("Text") or "").strip()
                if not t:
                    continue
                key = t[:120]
                if key in seen:
                    continue
                seen.add(key)
                lines.append(f"- {t}")
                if len(seen) >= 3:
                    break
            lines.append("")

        lines.append("Ações e recomendações disparadas pelas respostas:")
        for q in dom.get("questions", []):
            qid = q["question_id"]
            score = q["score"]
            th = q.get("theory", {}) or {}
            action_code = th.get("action_code")
            action_desc = th.get("action_description")
            expl = th.get("explanation")
            obj = th.get("objective")

            lines.append(f"- {qid} | score {score}:")
            if expl:
                lines.append(f"  Explicação: {expl}")
            if obj:
                lines.append(f"  Objetivo: {obj}")
            if action_code:
                lines.append(f"  Ação: {action_code} | {action_desc}")
            else:
                lines.append("  Ação: (nenhuma ação associada nesta base teórica)")

            comments = q.get("comments") or []
            if comments:
                lines.append("  Comentários relevantes:")
                for c in comments[:3]:
                    txt = (c.get("text") or "").strip()
                    if txt:
                        lines.append(f"  - {txt}")
            lines.append("")

        next_level = min(5, level + 1)
        lines.append(f"Rumo ao próximo nível: {next_level}")
        lines.append("Notas:")
        lines.append("- O nível do domínio é calculado por floor(média).")
        lines.append("- A evolução de maturidade exige evidências consistentes ao longo das questões do domínio.")
        return "\n".join(lines).strip()

    def _compose_conclusion_text(self, model: Dict[str, Any]) -> str:
        scores = model.get("scores", {})
        doms = model.get("domains", [])
        lines: List[str] = []
        lines.append("Conclusão e próximos passos.")
        lines.append(f"Score global: {scores.get('global_avg', 0):.2f} | Nível global (floor): {scores.get('global_level', 0)}.")
        lines.append("")
        lines.append("Prioridades sugeridas (heurística):")
        doms_sorted = sorted(doms, key=lambda d: (d.get("level", 0), d.get("avg", 0)))
        for d in doms_sorted[:5]:
            lines.append(f"- {d['acronym']} (nível {d['level']}, média {d['avg']:.2f})")
        lines.append("")
        lines.append("Próximos passos:")
        lines.append("- Validar evidências e artefatos para cada ação recomendada.")
        lines.append("- Priorizar correções estruturais onde há dependências com desalinhamento de nível.")
        lines.append("- Planejar roadmap por ondas (curto, médio, longo prazo) alinhado à estratégia de dados.")
        return "\n".join(lines).strip()

    # ----------------------------
    # HELPERS do DOCX BUILDER
    # ----------------------------


    def _get_project_name(self, project_id: str) -> str:
        projects = self.repo.fetch_all("projects") or []
        for p in projects:
            if str(p.get("project_id")) == str(project_id):
                return p.get("name") or project_id
        return project_id

    def _get_user_full_name(self, user_id: Optional[str]) -> str:
        if not user_id:
            return ""
        users = self.repo.fetch_all("users") or []
        for u in users:
            if str(u.get("email_hash")) == str(user_id):
                return u.get("full_name") or ""
        return ""

    # ----------------------------
    # DOCX BUILDER
    # ----------------------------


    # ----------------------------
    # REPORT JSON PIPELINE (EN -> optional translation) + PACKAGE
    # ----------------------------

    def _report_json_cache_path(self, project_id: str, scope: str, user_id: Optional[str], model_hash: str) -> Path:
        return _cache_dir(self.base_dir, project_id, scope, user_id) / f"report_json_enriched_{model_hash}.json"

    def _translation_cache_path(self, project_id: str, scope: str, user_id: Optional[str], model_hash: str, target_language: str) -> Path:
        return _cache_dir(self.base_dir, project_id, scope, user_id) / f"report_json_translated_{target_language}_{model_hash}.json"

    def _build_report_json_from_model(self, model: Dict[str, Any]) -> Dict[str, Any]:
        """Builds the FULL report JSON in ENGLISH (deterministic)."""
        meta = model.get("meta", {}) or {}
        scores = model.get("scores", {}) or {}
        domains = model.get("domains", []) or []

        labels = {
            "report_title": "DOMMx Final Assessment Report",
            "table_of_contents": "Table of Contents",
            "chapter_1": "1. Introduction",
            "chapter_1_1": "1.1 DOMMx context",
            "chapter_1_2": "1.2 Assessment method",
            "chapter_2": "2. Consolidated Results",
            "chapter_2_1": "2.1 Scores by domain",
            "chapter_2_2": "2.2 Global score",
            "chapter_2_3": "2.3 Maturity radar",
            "chapter_3": "3. Dependencies and Structural Inconsistencies",
            "chapter_4": "4. Domain Analysis",
            "chapter_5": "5. Overall Conclusion",
            "score_avg": "Average score",
            "level_floor": "Level (floor)",
            "criteria_evaluated": "Evaluated criteria",
            "domain_conclusion": "Conclusion",
            "recommended_action": "Recommended action",
            "processes": "Processes",
            "prerequisites": "Prerequisites",
            "deliverables": "Deliverables",
            "recommendations": "Recommendations",
            "notes": "Notes",
            "final_synthesis": "Final synthesis",
            "next_steps": "Next steps",
            "no_inconsistencies": "No relevant structural inconsistencies were identified across the evaluated domains.",
        }

        # Chapter 1 text (EN, concise)
        intro_context = (
            "This report presents the maturity diagnosis for data governance and data management using the DOMMx "
            "(Data Operating Model and Maturity). DOMMx consolidates widely adopted market practices and recognized "
            "frameworks, including DAMA-DMBOK2 and DCAM, providing a domain-based view of capability adoption and maturity."
        )
        intro_method = (
            "Scores are aggregated at the domain level. The domain level is computed using floor(average score), "
            "a conservative and audit-friendly approach. Dependencies between domains reflect consolidated practices "
            "from DAMA-DMBOK2, DCAM, and other commonly adopted market standards."
        )

        # Chapter 3 deterministic dependency text (EN)
        deps_text = self._compose_dependencies_text_en(domains, labels)

        # Domain order already in model (sorted by flow sequence)
        domains_json: List[Dict[str, Any]] = []
        for d in domains:
            ac = d.get("acronym")
            avg = float(d.get("avg", 0.0))
            lvl = int(d.get("level", 0))

            # Criteria: objectives from answered questions (dedup, keep order)
            objectives: List[str] = []
            for q in d.get("questions", []) or []:
                obj = (q.get("theory") or {}).get("objective")
                if obj:
                    objectives.append(str(obj).strip())
            # dedup
            seen = set()
            criteria = []
            for o in objectives:
                if o and o not in seen:
                    seen.add(o)
                    criteria.append(o)

            # Action code by domain level: first matching level_entries Action_Code
            action_code, action_title = self._pick_action_for_domain(d, lvl)

            # Load action catalog (EN base = 'us')
            action_payload = self._load_action_from_catalog(acronym=str(ac), action_code=action_code, catalog_lang="us")

            domains_json.append({
                "acronym": str(ac),
                "name": str(d.get("name") or ac),
                "avg_score": avg,
                "level": lvl,
                "level_label": self._get_level_label_en(lvl),
                "criteria_objectives": criteria,           # raw objectives list (EN)
                "criteria_summary": "",                    # AI will fill (EN)
                "domain_conclusion": "",                   # AI will fill (EN)
                "recommended_action": {
                    "code": action_code,
                    "title": action_title,
                    "procedures": action_payload.get("procedures", []),
                },
                "final_synthesis": "",                     # AI will fill (EN)
                "next_steps": "",                          # AI will fill (EN)
            })

        report_json = {
            "labels": labels,
            "meta": {
                **meta,
                "language": "en",
            },
            "scores": {
                "global_avg": float(scores.get("global_avg", 0.0)),
                "global_level": int(scores.get("global_level", 0)),
            },
            "chapters": {
                "introduction": {
                    "context": intro_context,
                    "method": intro_method,
                },
                "dependencies": {
                    "text": deps_text,
                },
                "overall_conclusion": {
                    "text": "",  # AI optional? we keep deterministic short later
                },
            },
            "domains": domains_json,
        }

        # deterministic overall conclusion (EN, half page max)
        report_json["chapters"]["overall_conclusion"]["text"] = self._compose_overall_conclusion_en(report_json)

        return report_json

    def _compose_dependencies_text_en(self, domains: List[Dict[str, Any]], labels: Dict[str, str]) -> str:
        inconsistencies: List[str] = []

        for d in domains:
            for da in d.get("dependency_analysis", []) or []:
                item = da.get("json_item") or {}
                scenario_key = da.get("scenario_key")
                if not scenario_key:
                    continue

                scenarios = item.get("scenarios") or {}
                scenario = scenarios.get(scenario_key) if isinstance(scenarios, dict) else None
                analysis = ""
                if isinstance(scenario, dict):
                    analysis = (scenario.get("analysis_text") or scenario.get("whynot_text") or "").strip()

                primary = da.get("primary_acronym") or d.get("acronym")
                reference = da.get("reference_acronym")
                primary_level = da.get("primary_level")
                reference_level = da.get("reference_level")

                # treat inconsistency if scenario_key is not 'ok' and analysis exists
                if analysis and scenario_key not in ("ok", "consistent", "no_issue"):
                    inconsistencies.append(
                        f"{primary} (level {primary_level}) vs {reference} (level {reference_level}): {analysis}"
                    )

        if not inconsistencies:
            return labels["no_inconsistencies"]

        lines = ["Structural inconsistencies were identified:"]
        for s in inconsistencies:
            lines.append(f"- {s}")
        lines.append("")
        lines.append("Recommended correction is to address prerequisite domains first, then progressively stabilize dependent domains.")
        return "\n".join(lines).strip()

    def _compose_overall_conclusion_en(self, report_json: Dict[str, Any]) -> str:
        gavg = report_json.get("scores", {}).get("global_avg", 0.0)
        glvl = report_json.get("scores", {}).get("global_level", 0)

        lines = []
        lines.append(f"The consolidated diagnosis indicates a global level {glvl} with an average score of {gavg:.2f}.")
        lines.append("Maturity is uneven across domains, with clear opportunities for structural strengthening.")
        lines.append("Prioritization should consider lower-level domains and any identified dependency gaps.")
        lines.append("Executing the recommended actions with evidence-based deliverables enables consistent progression to the next maturity level.")
        return "\n\n".join(lines)

    def _get_level_label_en(self, level: int) -> str:
        labels = {
            0: "Initial",
            1: "Ad Hoc",
            2: "Repeatable",
            3: "Defined",
            4: "Managed",
            5: "Optimized",
        }
        return labels.get(int(level), str(level))

    def _pick_action_for_domain(self, domain_model: Dict[str, Any], level: int) -> Tuple[str, str]:
        # Primary source: level_entries filtered by level (already in model)
        for e in domain_model.get("level_entries", []) or []:
            if str(e.get("Action_Code") or "").strip():
                return str(e.get("Action_Code")).strip(), str(e.get("Action_Description") or "").strip()

        # Fallback: any action attached to questions
        for a in domain_model.get("actions", []) or []:
            if str(a.get("action_code") or "").strip():
                return str(a.get("action_code")).strip(), str(a.get("action_description") or "").strip()

        return "", ""

    def _load_action_from_catalog(self, acronym: str, action_code: str, catalog_lang: str = "us") -> Dict[str, Any]:
        if not action_code:
            return {"procedures": []}

        path = Path(self.base_dir) / "data" / "domains" / catalog_lang / f"{acronym}_action_catalog.yaml"
        if not path.exists():
            return {"procedures": []}

        payload = load_yaml_file(str(path)) or {}
        catalog = payload.get("action_catalog") or {}
        action = catalog.get(action_code) or {}
        procedures = action.get("procedures") or []
        out = []

        # Normalize procedures into a stable list structure
        for p in procedures:
            if not isinstance(p, dict):
                continue
            out.append({
                "number": p.get("number"),
                "name": p.get("name"),
                "prerequisite": p.get("prerequisite"),
                "deliverable": p.get("deliverable"),
                "recommendations": p.get("recommendations") or [],
                "notes": p.get("notes") or [],
            })

        return {"procedures": out}

    def _enrich_report_json_with_ai(self, report_json: Dict[str, Any], model_hash: str, force_regen: bool = False) -> Dict[str, Any]:
        """
        Enrichment A only (EN):
        - criteria_summary (from objectives)
        - domain_conclusion
        - final_synthesis + next_steps
        Uses cache to avoid repeated calls.
        """
        meta = report_json.get("meta", {}) or {}
        project_id = str(meta.get("project_id") or meta.get("project") or "")
        scope = str(meta.get("scope") or "user")
        user_id = meta.get("user_id")

        # cache file
        cpath = self._report_json_cache_path(project_id, scope, user_id, model_hash)
        if cpath.exists() and not force_regen:
            try:
                return json.loads(cpath.read_text(encoding="utf-8"))
            except Exception:
                pass

        if not self.ai_call:
            # deterministic fallback
            for d in report_json.get("domains", []) or []:
                d["criteria_summary"] = self._fallback_criteria_summary(d.get("criteria_objectives") or [])
                d["domain_conclusion"] = self._fallback_domain_conclusion(d.get("level", 0))
                d["final_synthesis"] = self._fallback_final_synthesis(d.get("level", 0))
                d["next_steps"] = self._fallback_next_steps(d.get("level", 0))
            cpath.write_text(json.dumps(report_json, ensure_ascii=False, indent=2), encoding="utf-8")
            return report_json

        from concurrent.futures import ThreadPoolExecutor, as_completed

        def enrich_one(dom: Dict[str, Any]) -> Dict[str, Any]:
            level = int(dom.get("level", 0))
            criteria = dom.get("criteria_objectives") or []
            action = dom.get("recommended_action") or {}
            procedures = action.get("procedures") or []

            # 1) criteria summary
            dom["criteria_summary"] = self._ai_summarize_criteria(criteria)

            # 2) domain conclusion (short, assertive)
            dom["domain_conclusion"] = self._ai_domain_conclusion(dom.get("acronym"), dom.get("name"), level, criteria)

            # 3) final synthesis + next steps (short)
            dom["final_synthesis"], dom["next_steps"] = self._ai_domain_synthesis(dom.get("acronym"), level, action.get("code"), procedures)

            return dom

        domains = report_json.get("domains", []) or []
        out_domains = []

        with ThreadPoolExecutor(max_workers=self.ai_workers) as ex:
            futs = [ex.submit(enrich_one, d) for d in domains]
            for fut in as_completed(futs):
                try:
                    out_domains.append(fut.result())
                except Exception:
                    # keep original domain if AI fails
                    pass

        # Preserve original ordering
        by_ac = {d["acronym"]: d for d in out_domains if isinstance(d, dict) and d.get("acronym")}
        final_domains = []
        for d in domains:
            final_domains.append(by_ac.get(d.get("acronym"), d))
        report_json["domains"] = final_domains

        cpath.write_text(json.dumps(report_json, ensure_ascii=False, indent=2), encoding="utf-8")
        return report_json

    def _ai_summarize_criteria(self, objectives: List[str]) -> str:
        if not objectives:
            return "- (no criteria available)"

        prompt = (
            "Summarize the evaluated criteria below as a concise bullet list.\n"
            "Rules:\n"
            "- Do not add new criteria\n"
            "- Keep each bullet short (max 10 words)\n"
            "- Return 5 to 10 bullets\n"
            "- Output bullets only, no intro text\n\n"
            "CRITERIA:\n" + "\n".join(f"- {o}" for o in objectives)
        )
        base_text = "\n".join(f"- {o}" for o in objectives[:10])
        return self._call_ai_safe(prompt, base_text)

    def _ai_domain_conclusion(self, acronym: str, name: str, level: int, objectives: List[str]) -> str:
        prompt = (
            "Write a short, assertive domain conclusion (3-5 sentences) for an audit report.\n"
            "Rules:\n"
            "- Do not repeat the score value\n"
            "- Focus on what exists today and what is missing\n"
            "- No fluff\n"
            "- English\n\n"
            f"DOMAIN: {acronym} - {name}\n"
            f"LEVEL: {level}\n"
            "EVALUATED CRITERIA (objectives):\n" + "\n".join(f"- {o}" for o in objectives)
        )
        base_text = self._fallback_domain_conclusion(level)
        return self._call_ai_safe(prompt, base_text)

    def _ai_domain_synthesis(self, acronym: str, level: int, action_code: str, procedures: List[Dict[str, Any]]) -> Tuple[str, str]:
        next_level = min(5, int(level) + 1)
        proc_names = [p.get("name") for p in procedures if isinstance(p, dict) and p.get("name")]
        proc_preview = "\n".join(f"- {n}" for n in proc_names[:8]) if proc_names else "- (no procedures)"

        prompt = (
            "Produce two short sections for an audit report: Final synthesis and Next steps.\n"
            "Rules:\n"
            "- Each section max 3 sentences\n"
            "- Be concrete and action-oriented\n"
            "- Do not invent procedures beyond the provided list\n"
            "- English\n\n"
            f"DOMAIN: {acronym}\n"
            f"CURRENT LEVEL: {level}\n"
            f"NEXT LEVEL TARGET: {next_level}\n"
            f"RECOMMENDED ACTION: {action_code}\n"
            "PROCEDURES:\n" + proc_preview + "\n\n"
            "Return JSON only with keys: final_synthesis, next_steps."
        )

        base = {
            "final_synthesis": self._fallback_final_synthesis(level),
            "next_steps": self._fallback_next_steps(level),
        }

        try:
            raw = self._call_ai_safe(prompt, json.dumps(base))
            parsed = json.loads(raw)
            fs = str(parsed.get("final_synthesis", base["final_synthesis"])).strip()
            ns = str(parsed.get("next_steps", base["next_steps"])).strip()
            return fs, ns
        except Exception:
            return base["final_synthesis"], base["next_steps"]

    def _fallback_criteria_summary(self, objectives: List[str]) -> str:
        if not objectives:
            return "- (no criteria available)"
        out = []
        for o in objectives[:10]:
            out.append(f"- {o}")
        return "\n".join(out)

    def _fallback_domain_conclusion(self, level: int) -> str:
        lvl = int(level)
        if lvl <= 1:
            return "Practices are mostly informal and depend on individuals. Controls and evidence are limited. Formal roles and governance routines are not consistently established."
        if lvl == 2:
            return "Core practices exist but are inconsistently applied. Evidence is partial and governance routines are not fully institutionalized. Standardization and monitoring require strengthening."
        if lvl == 3:
            return "Practices are defined and documented, with clearer roles and repeatable routines. Consistency improves, but measurement and control can be strengthened to ensure sustained adoption."
        if lvl == 4:
            return "Practices are managed with monitoring and performance control. Evidence and routines are consistent. Optimization opportunities exist to reduce friction and improve outcomes."
        return "Practices are optimized and continuously improved. Controls and evidence are mature and consistently applied across the organization."

    def _fallback_final_synthesis(self, level: int) -> str:
        next_level = min(5, int(level) + 1)
        return f"Progressing to level {next_level} requires consistent execution, formal evidence, and institutionalized controls aligned to the recommended action."

    def _fallback_next_steps(self, level: int) -> str:
        return "Establish ownership, publish the required artefacts, execute procedures consistently, and monitor adherence with periodic review."

    def _call_ai_safe(self, prompt: str, base_text: str) -> str:
        messages = [
            {"role": "system", "content": "Return only the requested output. No extra text."},
            {"role": "user", "content": prompt},
        ]
        last_err = None
        for attempt in range(1, self.ai_retries + 1):
            try:
                return self._call_ai_with_timeout(messages)
            except Exception as e:
                last_err = e
                time.sleep(0.4 * attempt)
        return base_text

    def _translate_full_report_json(
        self,
        report_json: Dict[str, Any],
        model_hash: str,
        target_language: str,
        force_regen: bool = False
    ) -> Dict[str, Any]:
        meta = report_json.get("meta", {}) or {}
        project_id = str(meta.get("project_id") or meta.get("project") or "")
        scope = str(meta.get("scope") or "user")
        user_id = meta.get("user_id")

        cpath = self._translation_cache_path(project_id, scope, user_id, model_hash, target_language)
        if cpath.exists() and not force_regen:
            try:
                return json.loads(cpath.read_text(encoding="utf-8"))
            except Exception:
                pass

        if not self.ai_call:
            # no AI -> no translation
            return report_json

        prompt = (
            "Translate the JSON below to the target language.\n"
            "Rules:\n"
            "- Do NOT change JSON keys\n"
            "- Do NOT change numbers\n"
            "- Do NOT change codes (domain acronyms, action codes, procedure numbers)\n"
            "- Translate only the string values\n"
            "- Return valid JSON only\n\n"
            f"TARGET_LANGUAGE: {target_language}\n\n"
            + json.dumps(report_json, ensure_ascii=False)
        )

        messages = [
            {"role": "system", "content": "Return valid JSON only. No explanations."},
            {"role": "user", "content": prompt},
        ]

        translated_raw = None
        last_err = None
        for attempt in range(1, self.ai_retries + 1):
            try:
                translated_raw = self._call_ai_with_timeout(messages)
                parsed = json.loads(translated_raw)
                cpath.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
                return parsed
            except Exception as e:
                last_err = e
                time.sleep(0.4 * attempt)

        return report_json

    def _render_docx_from_report_json(self, out_path: Path, report_json: Dict[str, Any]) -> None:
        """DOCX builder only. No AI, no translation."""
        if Document is None:
            raise RuntimeError("python-docx not available")

        labels = report_json.get("labels", {}) or {}
        meta = report_json.get("meta", {}) or {}
        scores = report_json.get("scores", {}) or {}
        chapters = report_json.get("chapters", {}) or {}
        domains = report_json.get("domains", []) or []

        doc = Document()

        # Cover
        title = labels.get("report_title", "DOMMx Final Assessment Report")
        doc.add_heading(title, level=0)

        project_name = self._get_project_name(meta.get("project_id") or meta.get("project"))
        user_full_name = self._get_user_full_name(meta.get("user_id"))

        doc.add_paragraph(f"Project: {project_name}")
        if user_full_name:
            doc.add_paragraph(f"Assessed by: {user_full_name}")
        doc.add_paragraph(f"Scope: {meta.get('scope', '')}")
        doc.add_paragraph(f"Generated: {meta.get('generated_at', '')}")
        doc.add_paragraph(f"Engine version: {meta.get('report_engine_version', REPORT_ENGINE_VERSION)}")

        doc.add_page_break()

        # TOC (updates when opening Word)
        doc.add_heading(labels.get("table_of_contents", "Table of Contents"), level=1)
        _docx_add_toc(doc)
        doc.settings.element.append(OxmlElement("w:updateFields"))
        doc.add_page_break()

        # Chapter 1
        doc.add_heading(labels.get("chapter_1", "1. Introduction"), level=1)
        doc.add_heading(labels.get("chapter_1_1", "1.1 DOMMx context"), level=2)
        doc.add_paragraph((chapters.get("introduction", {}) or {}).get("context", ""))

        doc.add_heading(labels.get("chapter_1_2", "1.2 Assessment method"), level=2)
        doc.add_paragraph((chapters.get("introduction", {}) or {}).get("method", ""))

        # Chapter 2
        doc.add_page_break()
        doc.add_heading(labels.get("chapter_2", "2. Consolidated Results"), level=1)

        doc.add_heading(labels.get("chapter_2_1", "2.1 Scores by domain"), level=2)
        # Simple table
        tbl = doc.add_table(rows=1, cols=5)
        hdr = tbl.rows[0].cells
        hdr[0].text = "#"
        hdr[1].text = "Domain"
        hdr[2].text = "Name"
        hdr[3].text = labels.get("score_avg", "Average score")
        hdr[4].text = labels.get("level_floor", "Level (floor)")

        for i, d in enumerate(domains, start=1):
            row = tbl.add_row().cells
            row[0].text = str(i)
            row[1].text = str(d.get("acronym"))
            row[2].text = str(d.get("name"))
            row[3].text = f"{float(d.get('avg_score', 0.0)):.2f}"
            row[4].text = f"{int(d.get('level', 0))}"

        doc.add_paragraph("")

        doc.add_heading(labels.get("chapter_2_2", "2.2 Global score"), level=2)
        doc.add_paragraph(f"{labels.get('score_avg','Average score')}: {float(scores.get('global_avg',0.0)):.2f}")
        doc.add_paragraph(f"{labels.get('level_floor','Level (floor)')}: {int(scores.get('global_level',0))}")

        # Radar
        doc.add_heading(labels.get("chapter_2_3", "2.3 Maturity radar"), level=2)
        radar_buf = self._try_build_radar_png(domains)
        if radar_buf is not None:
            try:
                doc.add_picture(radar_buf)
            except Exception:
                pass

        # Chapter 3
        doc.add_page_break()
        doc.add_heading(labels.get("chapter_3", "3. Dependencies and Structural Inconsistencies"), level=1)
        doc.add_paragraph((chapters.get("dependencies", {}) or {}).get("text", ""))

        # Chapter 4
        doc.add_page_break()
        doc.add_heading(labels.get("chapter_4", "4. Domain Analysis"), level=1)

        for d in domains:
            ac = d.get("acronym")
            name = d.get("name")
            doc.add_heading(f"{ac} – {name}", level=2)

            doc.add_paragraph(f"{labels.get('score_avg','Average score')}: {float(d.get('avg_score',0.0)):.2f}")
            doc.add_paragraph(f"{labels.get('level_floor','Level (floor)')}: {int(d.get('level',0))} – {d.get('level_label','')}")
            doc.add_paragraph("")

            # Criteria evaluated (summary bullets)
            doc.add_heading(labels.get("criteria_evaluated","Evaluated criteria"), level=3)
            criteria_summary = (d.get("criteria_summary") or "").strip()
            if criteria_summary:
                for line in criteria_summary.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    if not line.startswith("-"):
                        line = "- " + line
                    doc.add_paragraph(line[1:].strip(), style="List Bullet")
            else:
                for o in d.get("criteria_objectives", [])[:10]:
                    doc.add_paragraph(str(o), style="List Bullet")

            doc.add_paragraph("")

            # Domain conclusion
            doc.add_heading(labels.get("domain_conclusion","Conclusion"), level=3)
            doc.add_paragraph((d.get("domain_conclusion") or "").strip())
            doc.add_paragraph("")

            # Recommended action
            ra = d.get("recommended_action") or {}
            if ra.get("code"):
                doc.add_heading(labels.get("recommended_action","Recommended action"), level=3)
                doc.add_paragraph(f"{ra.get('code')} – {ra.get('title','')}".strip())
                doc.add_paragraph("")

                doc.add_heading(labels.get("processes","Processes"), level=3)
                for p in ra.get("procedures", []) or []:
                    pname = p.get("name") or ""
                    pnum = p.get("number")
                    doc.add_heading(f"Proc {pnum} – {pname}".strip(), level=4)

                    # prerequisite
                    prereq = (p.get("prerequisite") or "").strip()
                    if prereq:
                        doc.add_paragraph(f"{labels.get('prerequisites','Prerequisites')}: {prereq}")

                    # deliverable
                    deliverable = (p.get("deliverable") or "").strip()
                    if deliverable:
                        doc.add_paragraph(f"{labels.get('deliverables','Deliverables')}: {deliverable}")

                    # recommendations
                    recs = p.get("recommendations") or []
                    if recs:
                        doc.add_paragraph(labels.get("recommendations","Recommendations") + ":")
                        for r in recs:
                            doc.add_paragraph(str(r), style="List Bullet")

                    # notes
                    notes = p.get("notes") or []
                    if notes:
                        doc.add_paragraph(labels.get("notes","Notes") + ":")
                        for n in notes:
                            doc.add_paragraph(str(n), style="List Bullet")

                    doc.add_paragraph("")

            # Final synthesis + next steps
            doc.add_heading(labels.get("final_synthesis","Final synthesis"), level=3)
            doc.add_paragraph((d.get("final_synthesis") or "").strip())
            doc.add_heading(labels.get("next_steps","Next steps"), level=3)
            doc.add_paragraph((d.get("next_steps") or "").strip())
            doc.add_page_break()

        # Chapter 5
        doc.add_heading(labels.get("chapter_5", "5. Overall Conclusion"), level=1)
        doc.add_paragraph((chapters.get("overall_conclusion", {}) or {}).get("text", ""))

        out_path.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(out_path))

    def _try_build_radar_png(self, domains: List[Dict[str, Any]]):
        try:
            import numpy as np  # type: ignore
            import matplotlib.pyplot as plt  # type: ignore
            from io import BytesIO
        except Exception:
            return None

        if not domains:
            return None

        labels = [str(d.get("acronym")) for d in domains]
        values = [float(d.get("avg_score", 0.0)) for d in domains]
        if len(labels) < 3:
            return None

        # close loop
        labels2 = labels + labels[:1]
        values2 = values + values[:1]
        angles = np.linspace(0, 2 * np.pi, len(labels2), endpoint=True)

        fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True))
        ax.plot(angles, values2)
        ax.fill(angles, values2, alpha=0.25)
        ax.set_ylim(0, 5)

        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(labels)

        buf = BytesIO()
        plt.tight_layout()
        plt.savefig(buf, format="png", dpi=200)
        plt.close(fig)
        buf.seek(0)
        return buf

    def _try_convert_docx_to_pdf(self, docx_path: Path) -> Optional[Path]:
        """Best-effort DOCX->PDF conversion using LibreOffice (soffice)."""
        import shutil
        import subprocess

        soffice = shutil.which("soffice") or shutil.which("libreoffice")
        if not soffice:
            return None

        outdir = docx_path.parent
        try:
            subprocess.run(
                [soffice, "--headless", "--convert-to", "pdf", str(docx_path), "--outdir", str(outdir)],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            pdf_path = outdir / (docx_path.stem + ".pdf")
            return pdf_path if pdf_path.exists() else None
        except Exception:
            return None

    def _build_zip_package(self, docx_path: Path, pdf_path: Optional[Path]) -> Path:
        import zipfile

        zip_path = docx_path.with_suffix(".zip")
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.write(str(docx_path), arcname=docx_path.name)
            if pdf_path and pdf_path.exists():
                z.write(str(pdf_path), arcname=pdf_path.name)
        return zip_path


    def _build_docx(self, out_path: Path, model: Dict[str, Any], narratives: Dict[str, Any]) -> None:
        out_path.parent.mkdir(parents=True, exist_ok=True)

        doc = Document()        

        meta = model.get("meta", {})
        project_id = meta.get("project_id")
        scope = meta.get("scope")
        user_id = meta.get("user_id")
        
        project_name = self._get_project_name(project_id)
        user_full_name = self._get_user_full_name(user_id)      

        doc.add_heading("DOMMx Assessment Report", level=1)
        _docx_add_kv_table(doc, [
            ("Project", project_name),
            ("Assessed By", user_full_name if user_full_name else ""),
            ("Scope", str(scope)),
            ("Generated at (UTC)", str(meta.get("generated_at"))),
            ("Report Engine Version", REPORT_ENGINE_VERSION),
        ])

        doc.add_paragraph("")
        doc.add_heading("Sumário", level=2)
        
        _docx_add_toc(doc)
        doc.settings.element.append(OxmlElement("w:updateFields"))
        
        doc.add_page_break()

        doc.add_heading("1. Introdução", level=1)
        doc.add_heading("1.1 Contexto", level=2)
        doc.add_paragraph(
            "Este relatório consolida os resultados do assessment DOMMx, "
            "com foco em maturidade por domínio e coerência estrutural entre domínios."
        )
        doc.add_heading("1.2 Metodologia de Cálculo", level=2)
        doc.add_paragraph(
            "O nível de maturidade por domínio é calculado a partir da média das respostas do domínio "
            "e convertido para nível discreto utilizando floor(média), abordagem conservadora e auditável."
        )
        doc.add_paragraph(
            "A sequência dos domínios e suas dependências segue o arquivo de orquestração do modelo (flow.yaml)."
        )

        doc.add_heading("2. Visão Geral dos Resultados", level=1)
        ov = narratives.get("overview", {}).get("text") if isinstance(narratives.get("overview"), dict) else ""
        if ov:
            doc.add_paragraph(ov)

        doc.add_heading("2.1 Scores por Domínio", level=2)
        domain_rows = [
            {"sequence": d.get("sequence"), "acronym": d.get("acronym"), "name": d.get("name"), "avg": d.get("avg"), "level": d.get("level")}
            for d in model.get("domains", [])
        ]
        _docx_add_score_table(doc, domain_rows)

        doc.add_heading("2.2 Score Global", level=2)
        gs = model.get("scores", {})
        doc.add_paragraph(f"Score global: {gs.get('global_avg', 0):.2f}")
        doc.add_paragraph(f"Nível global (floor): {gs.get('global_level', 0)}")
        doc.add_page_break()

        doc.add_heading("3. Análise de Dependências e Inconsistências", level=1)
        dep_txt = narratives.get("dependencies", {}).get("text") if isinstance(narratives.get("dependencies"), dict) else ""
        if dep_txt:
            doc.add_paragraph(dep_txt)

        doc.add_heading("3.1 Conclusão da Análise Estrutural", level=2)
        doc.add_paragraph(
            "As inconsistências indicadas nesta seção derivam do cruzamento entre níveis (floor) do domínio primário "
            "e de seus domínios de referência conforme dependências estruturais definidas no flow.yaml."
        )
        doc.add_page_break()

        doc.add_heading("4. Análise Detalhada por Domínio", level=1)

        for dom in model.get("domains", []):
            ac = dom["acronym"]
            doc.add_heading(f"4.{dom.get('sequence')} {ac} — {dom.get('name')}", level=2)

            doc.add_heading("Score e Nível", level=3)
            doc.add_paragraph(f"Média: {dom.get('avg', 0):.2f}")
            doc.add_paragraph(f"Nível (floor): {dom.get('level', 0)}")

            doc.add_heading("Posição Estrutural e Dependências", level=3)
            deps = dom.get("dependence_acronyms", []) or []
            doc.add_paragraph(f"Dependências (ordem): {', '.join(deps) if deps else 'nenhuma'}")

            dom_txt = narratives.get("domains", {}).get(ac, {}).get("text") if isinstance(narratives.get("domains", {}).get(ac), dict) else ""
            if dom_txt:
                doc.add_heading("Interpretação e Recomendações", level=3)
                doc.add_paragraph(dom_txt)

            refs = dom.get("cross_references", {}).get("by_type", {})
            if refs:
                doc.add_heading("Referências Cruzadas (Resumo)", level=3)
                for t, items in refs.items():
                    if not items:
                        continue
                    doc.add_paragraph(f"{t}:")
                    for r in items[:8]:
                        doc.add_paragraph(str(r), style="List Bullet")

            doc.add_paragraph("")

        doc.add_heading("5. Conclusão e Próximos Passos", level=1)
        concl_txt = narratives.get("conclusion", {}).get("text") if isinstance(narratives.get("conclusion"), dict) else ""
        if concl_txt:
            doc.add_paragraph(concl_txt)

        doc.save(str(out_path))