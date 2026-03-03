
# utils/theory_cluster_demo.py
# Purpose:
# - Input:  utils/theory-cluster/output/<DOMAIN>_theory_improved_output.json
# - Output: utils/theory-cluster/output/<DOMAIN>_theory_demo_output.json
# - Generate practical demo text per procedure
# - English only
# - Audit style, concise, realistic, document simulation
# - Cache + parallel + cost control

import os
import json
import time
import argparse
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv
from openai import OpenAI

print(">>> RUNNING FILE:", __file__)


# =========================================================
# PATHS
# =========================================================

BASE_DIR = Path(__file__).resolve().parent.parent.parent
THEORY_DIR = BASE_DIR / "utils" / "theory-cluster"
INPUT_DIR = THEORY_DIR / "output" / "improved"
OUTPUT_DIR = THEORY_DIR / "output" / "demo"
CACHE_DIR = THEORY_DIR / "_cache"

DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_MAX_WORKERS = 6
DEFAULT_BATCH_SIZE = 15

DEMO_CACHE_SUFFIX = "_theory_demo_cache.json"


# =========================================================
# Utils
# =========================================================

import sys

def render_progress_bar(current, total, start_time, bar_length=40):
    percent = current / total
    filled = int(bar_length * percent)
    bar = "#" * filled + "-" * (bar_length - filled)

    elapsed = time.time() - start_time
    avg = elapsed / current if current > 0 else 0
    remaining = total - current
    eta = int(avg * remaining)

    sys.stdout.write(
        f"\r[{bar}] {percent*100:5.1f}% "
        f"{current}/{total} "
        f"Elapsed: {int(elapsed)}s "
        f"ETA: {eta}s"
    )
    sys.stdout.flush()

    if current == total:
        print()  # newline when done
        
def log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)

def load_json(path: Path, default: Any):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path: Path, obj: Any):
    ensure_dir(path.parent)

    # Se existir, remove antes
    if path.exists():
        try:
            path.unlink()
        except PermissionError:
            time.sleep(0.5)
            path.unlink()

    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def sha256_text(s: str) -> str:
    return hashlib.sha256((s or "").encode()).hexdigest()

def openai_client() -> OpenAI:
    load_dotenv(BASE_DIR / ".env")
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# =========================================================
# Fingerprint
# =========================================================

def item_fingerprint(item: Dict[str, Any]) -> str:
    parts = [
        str(item.get("Domain") or ""),
        str(item.get("Action_Code") or ""),
        str(item.get("procedure") or ""),
        str(item.get("procedure_title") or ""),
        str(item.get("procedure_text") or ""),
        str(item.get("Score") or ""),
    ]
    return sha256_text("\n".join(parts))


# =========================================================
# Prompt
# =========================================================

SYSTEM_PROMPT = (
    "You are a senior Data Governance architect, auditor, and documentation specialist responsible for defining prescriptive Data Governance artifacts in medium and large organizations. "
    "Generate realistic corporate annotated structural blueprints for organizational documents. "
    "English only. Formal audit and corporate architecture tone. "
    "Concise, structured, operational, and prescriptive. "
    "Produce document structure with section purpose, expected content, and examples. "
    "No markdown. No commentary. "
    "Return plain text only."
)

def build_prompt(domain: str,
                 context: str,
                 score: int,
                 action_code: str,
                 action_title: str,
                 procedure_number: int,
                 procedure_title: str,
                 procedure_text: str) -> str:

    return f"""

Your task is to generate the realistic STANDARD DOCUMENT STRUCTURE of a prescriptive organizational document that defines a final Data Governance artifact derived from the specified procedure.

The output must represent an annotated structural blueprint formally adopted by organizations to implement this specific action and procedure within the given domain. The document must serve as a practical guide for creating the corresponding official Data Governance artifact.

This artifact originates from recommendations and notes describing a Data Governance procedure associated with an action catalog entry triggered by a maturity level assessment within a Data Governance domain.

The complete definition of the input Procedure is:

Domain: {domain}
Context: {context}
Score: {score}
Action Code: {action_code}
Action Title: {action_title}
Procedure Number: {procedure_number}
Procedure Title: {procedure_title}

Procedure Full Definition:
{procedure_text}


MATURITY SCORE STANDARDIZATION

Score 0 – Non-existent  
No formal Data Governance structure exists. Activities are ad hoc and reactive.

Score 1 – Initial  
Foundational governance principles are defined. Roles are identified but not institutionalized.

Score 2 – Defined  
Governance structures and decision authority are formally documented and approved. Processes exist but are not systematically measured.

Score 3 – Managed  
Governance processes are operational and repeatable. KPIs and monitoring mechanisms are defined and tracked.

Score 4 – Controlled  
Governance effectiveness is actively monitored and controlled. Metrics drive corrective action and structured review.

Score 5 – Optimized  
Governance is continuously improved using performance insights. Automation and measurable business impact are evident.


MATURITY BEHAVIOR ENGINE (MANDATORY ENFORCEMENT)

The document structure, control intensity, and language rigor MUST strictly follow the provided Score.

Behavioral Rules:

Score 0:
- No measurable KPIs.
- No operational monitoring.
- Section 7 may describe structural intent only.
- Section 7.4 MUST NOT appear.

Score 1:
- Governance elements identified but not institutionalized.
- Monitoring may be conceptual only.
- No measurable performance indicators.
- Section 7.4 MUST NOT appear.

Score 2:
- Governance formally defined and approved.
- Basic monitoring allowed.
- No performance targets.
- No optimization language.
- Section 7.4 MUST NOT appear.

Score 3:
- Monitoring and KPIs are mandatory.
- Escalation model must be operational.
- Compliance must reference structured internal controls.
- Section 7.4 MUST NOT appear.

Score 4:
- KPIs must include performance targets.
- Compliance must include audit mechanisms.
- Escalation must define accountability timelines.
- Section 7.4 MUST NOT appear.

Score 5:
- All Score 4 requirements apply.
- Section 7.4 becomes mandatory.
- 7.4 must demonstrate measurable institutionalization and continuous improvement.
- Must include evidence-based optimization.
- Must demonstrate governance contribution to business value or risk reduction.

Strict Prohibitions:
- No KPI language below Score 3.
- No performance targets below Score 4.
- No optimization language below Score 5.
- No placeholders such as “N/A” or “Not applicable”.
- No contradictions between declared Score and control intensity.


GOVERNANCE TERMINOLOGY STANDARDIZATION (MANDATORY)

The document MUST standardize governance terminology across all sections.
Terminology variation is NOT allowed unless explicitly justified by context.

Use the following baseline governance terminology consistently:

- Data Governance Council (primary decision authority body)
- Data Governance Office (operational coordination function)
- Data Owner (accountable authority for data domain decisions)
- Data Steward (operational data oversight role)
- Data Custodian (technical data management role)
- Governance Policy (formally approved governing document)
- Governance Standard (mandatory structural requirement)
- Governance Procedure (step-by-step execution structure)
- Governance Control (monitoring or enforcement mechanism)
- Escalation Pathway (formal decision escalation route)
- Internal Audit Function (independent compliance verification body)

Mandatory Rules:

1. Do NOT replace “Data Governance Council” with Board, Committee, or Steering Committee.
2. Do NOT introduce new governance body names unless explicitly required by the context.
3. Role naming must remain consistent throughout the document.
4. Use singular canonical naming for roles and structures.
5. Avoid synonyms that create semantic ambiguity.
6. Terminology must align with DAMA-DMBOK and enterprise governance best practices.
7. If the domain is not DG but another domain (e.g., DA, DQ, DS), governance bodies remain under the Data Governance Council umbrella unless explicitly stated otherwise.

Strict Prohibition:
- No inconsistent governance body names.
- No switching between Council, Committee, and Board.
- No informal role descriptions.
- No mixed terminology for the same structural element.


Structural Standardization Requirements

The document MUST always follow the fixed macro-structure below. Sections must not be removed or reordered. Subsection depth may increase according to maturity level.

1. Document Control
   1.1 Document Title
   1.2 Version and Status
   1.3 Approval Authority
   1.4 Revision History

2. Executive Summary

3. Domain and Context Framing
   3.1 Domain Definition
   3.2 Organizational Context
   3.3 Maturity Positioning (based on Score)

4. Action Definition
   4.1 Action Code and Title
   4.2 Action Objective
   4.3 Action Scope Boundaries

5. Procedure Definition
   5.1 Procedure Objective
   5.2 Prerequisites
   5.3 Deliverables
   5.4 Step-by-Step Execution Structure

6. Governance Structural Components
   6.1 Organizational Coverage
   6.2 Data Asset Coverage
   6.3 Governance Themes
   6.4 Governance Organizational Structure
   6.5 Decision Authority Model
   6.6 Governance Processes (bullet structured)
   6.7 Interfaces with Other Governance Structures
   6.8 Explicit Exclusions

7. Control and Oversight Mechanisms
   7.1 Monitoring and KPIs
   7.2 Compliance and Audit Alignment
   7.3 Escalation Model
   7.4 Evidence of Optimization and Institutionalization (ONLY when Score = 5)

8. Document Governance
   8.1 Lifecycle Management
   8.2 Review Cycle
   8.3 Ownership of the Document

9. Appendices
   9.1 Templates
   9.2 Reference Standards
   9.3 Supporting Artefacts


Instructions:

1. Produce the complete document structure typically adopted by mature organizations.
2. Structure the response using numbered sections exactly as defined.
3. Adapt depth and rigor strictly according to the provided Score.
4. For each section include:
   - Section title
   - Purpose
   - Expected content
   - Representative sample elements when applicable
5. Clearly differentiate Domain, Context, Action, and Procedure layers.
6. Governance Processes must be described using structured bullet points.
7. Avoid conceptual essays.
8. Ensure complementarity across procedures and logical maturity progression.
9. Use objective, normative corporate language.
10. Produce only the annotated structural blueprint.
11. Plain text only.

""".strip()


# =========================================================
# Demo Generation
# =========================================================

def generate_demo_batch(client: OpenAI,
                        model: str,
                        items: List[Dict[str, Any]],
                        cache_path: Path,
                        max_workers: int,
                        batch_size: int,
                        clear_cache: bool):

    ensure_dir(cache_path.parent)
    cache = load_json(cache_path, default={"generated": {}})
    generated = cache.setdefault("generated", {})

    if clear_cache:
        log("Clearing cache...")
        generated.clear()

    total = len(items)
    completed = 0
    start_time = time.time()

    to_call = []

    # Cache check
    for it in items:
        fp = item_fingerprint(it)
        if fp in generated:
            it["demo"] = generated[fp]
            it["_cache_hit"] = True
            completed += 1
        else:
            it["_cache_hit"] = False
            to_call.append(it)

    log(f"Total items: {total}")
    log(f"Cache hits: {completed}")
    log(f"To generate: {len(to_call)}")

    if total > 0:
        render_progress_bar(completed, total, start_time)

    def worker(it: Dict[str, Any]):
        fp = item_fingerprint(it)

        prompt = build_prompt(
            it["Domain"],
            it["Context"],
            it["Score"],
            it["Action_Code"],
            it.get("Action_Title", ""),
            it["procedure"],
            it["procedure_title"],
            it["procedure_text"]
        )

        resp = client.chat.completions.create(
            model=model,
            temperature=0,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ]
        )

        text = resp.choices[0].message.content.strip()

        # ===============================
        # Deterministic Maturity Injection
        # ===============================

        score = int(it["Score"])

        if score >= 3:
            text += governance_layer_score_3()

        if score >= 4:
            text += governance_layer_score_4()

        if score == 5:
            text += governance_layer_score_5()

        return fp, text

    if not to_call:
        log("All items served from cache.")
        return items

    batches = [to_call[i:i+batch_size] for i in range(0, len(to_call), batch_size)]

    for batch_index, batch in enumerate(batches, start=1):
        log(f"Starting batch {batch_index}/{len(batches)} | size={len(batch)}")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(worker, it): it for it in batch}

            for future in as_completed(futures):
                it = futures[future]
                fp = item_fingerprint(it)

                try:
                    fp2, text = future.result()
                    it["demo"] = text
                    generated[fp2] = text
                except Exception as e:
                    it["demo"] = ""
                    it["_error"] = str(e)
                    log(f"\nERROR for {it.get('Action_Code')} / P{it.get('procedure')} -> {e}")

                completed += 1
                render_progress_bar(completed, total, start_time)

        save_json(cache_path, cache)

    save_json(cache_path, cache)
    log("Generation completed.")
    return items

# =========================================================
# Orchestrator
# =========================================================

def build_score_map(items: list):
    action_codes = sorted(
        {it.get("Action_Code") for it in items if it.get("Action_Code")}
    )

    return {code: idx for idx, code in enumerate(action_codes)}
    

def run_domain(domain: str, model: str, max_workers: int,
               batch_size: int, clear_cache: bool):

    domain = domain.upper().strip()
    input_path = INPUT_DIR / f"{domain}_theory_improved_output.json"
    output_path = OUTPUT_DIR / f"{domain}_theory_demo_output.json"
    cache_path = CACHE_DIR / f"{domain}{DEMO_CACHE_SUFFIX}"

    if not input_path.exists():
        raise FileNotFoundError(f"Missing input: {input_path}")

    src = load_json(input_path, default={})
    items = src.get("items", [])

    demo_items = []          
    score_map = build_score_map(items)
        
    for it in items:
        procedures = it.get("Procedures", [])
        score = score_map.get(it.get("Action_Code"), 0)
        for p in procedures:
            demo_items.append({
                "Domain": it.get("Domain"),
                "Context": it.get("Context"),
                "Action_Code": it.get("Action_Code"),
                "Action_Title": it.get("Action_Title"),   
                "Score": score,                
                "procedure": p.get("procedure"),
                "procedure_title": p.get("procedure_title"),
                "procedure_text": p.get("text"),
                
                
            })
    
    print("DEBUG: total improved items =", len(items))
    print("DEBUG: total demo items =", len(demo_items))
    
    client = openai_client()

    demo_items = generate_demo_batch(
        client,
        model,
        demo_items,
        cache_path,
        max_workers,
        batch_size,
        clear_cache
    )

    final_output = []

    for it in demo_items:
        final_output.append({
            "domain": it.get("Domain"),
            "action_code": it.get("Action_Code"),
            "procedure": it.get("procedure"),
            "demo": it.get("demo", "")
        })

    save_json(output_path, {"items": final_output})
    log(f"Saved: {output_path}")



# =========================================================
# Governance Structural Patch Engine (Robust Version)
# =========================================================

import re


# ---------------------------------------------------------
# 1. Fix duplicated governance terms
# ---------------------------------------------------------

def _fix_duplicated_terms(text: str) -> str:
    """
    Remove duplicated words such as:
    'Data Governance Data Governance Council'
    """

    # Remove immediate duplicated sequences
    text = re.sub(
        r'\b(Data Governance Council)\s+\1\b',
        r'\1',
        text
    )

    text = re.sub(
        r'\b(Data Governance)\s+\1\b',
        r'\1',
        text
    )

    return text

# =========================================================
# Governance Layers (Deterministic Injection)
# =========================================================

def governance_layer_score_3():
    return """
10. Evidence Required
- Approved document with version control
- Formal approval record
- RACI matrix attached
- Repository registration ID
- Stakeholder validation evidence

11. Acceptance Criteria
- Document formally approved
- Scope clearly defined
- Roles validated
- Deliverables stored in official repository
- Communication recorded

12. Control Owner
- Primary Owner: Domain Owner or Data Governance Office
- Oversight Authority: Data Governance Council
- Escalation Path: Chief Data Officer
"""

def governance_layer_score_4():
    return """
13. Performance Metrics
- % of domains with approved artifacts
- % of reviews within SLA
- % of procedures with valid evidence
- Average update cycle time
- Non-compliance incidents per cycle

14. Monitoring Dashboard
- Domain compliance status
- Pending review alerts
- Governance heatmap
- KPI performance summary

15. Compliance Validation Cycle
- Mandatory semiannual review
- Annual internal audit
- Cross-domain validation
- RACI revalidation
- Escalation protocol
"""

def governance_layer_score_5():
    return """
16. Automation Layer
- Workflow-based approval system
- Automated versioning
- Automated review alerts
- Catalog integration
- Automated compliance tracking

17. Continuous Optimization
- Incident-driven refinement
- KPI trend analysis
- Maturity delta tracking
- Root cause analysis
- Improvement backlog

18. External Benchmark Alignment
- DCAM benchmark
- DMBOK gap analysis
- Independent review
- Peer comparison
- Regulatory verification
"""

# ---------------------------------------------------------
# 2. Normalize Section 7 structure based on maturity score
# ---------------------------------------------------------

def _rebuild_section_7(text: str, score: int) -> str:
    """
    Completely rebuild Section 7 deterministically based on maturity score.
    """

    lines = text.splitlines()
    new_lines = []
    inside_7 = False

    for line in lines:
        stripped = line.strip()

        # Detect beginning of section 7
        if stripped.startswith("7. Control and Oversight Mechanisms"):
            inside_7 = True
            continue

        # Detect beginning of section 8 (end of 7)
        if inside_7 and stripped.startswith("8. "):
            inside_7 = False
            new_lines.extend(_generate_section_7(score))
            new_lines.append(line)
            continue

        if not inside_7:
            new_lines.append(line)

    return "\n".join(new_lines)

def _generate_section_7(score: int) -> list:
    """
    Generate deterministic Section 7 structure by maturity score.
    Industrial structural differentiation for Scores 3–5.
    """

    block = []

    block.append("7. Control and Oversight Mechanisms")
    block.append("   Purpose: To define the formal control and oversight mechanisms applicable to this action.")

    # ----------------------------------------------------
    # SCORE 0–1 → Foundational only (unchanged)
    # ----------------------------------------------------
    if score in [0, 1]:
        block.append("   Expected Content: Basic governance oversight definition aligned with foundational maturity.")
        return block

    # ----------------------------------------------------
    # SCORE 2 → Defined (formalized, no KPIs, no targets)
    # ----------------------------------------------------
    if score == 2:
        block.append("   7.1 Monitoring Structure")
        block.append("       - Define documented monitoring approach without performance targets")
        block.append("       - Assign responsible governance roles")
        block.append("   7.2 Compliance and Audit Alignment")
        block.append("       - Define alignment with internal control and policy frameworks")
        block.append("   7.3 Escalation Model")
        block.append("       - Define formal escalation pathways and decision authority levels")
        return block

    # ----------------------------------------------------
    # SCORE 3 → Managed (operational and repeatable)
    # ----------------------------------------------------
    if score == 3:
        block.append("   7.1 Monitoring and KPIs")
        block.append("       - Define measurable indicators aligned with the action objective")
        block.append("       - Define measurement frequency and reporting cadence")
        block.append("       - Identify data source for each KPI")
        block.append("       - Assign accountable monitoring role")
        block.append("   7.2 Compliance and Internal Control Alignment")
        block.append("       - Reference structured internal control mechanisms")
        block.append("       - Define validation checkpoints")
        block.append("   7.3 Operational Escalation Model")
        block.append("       - Define escalation thresholds")
        block.append("       - Assign responsible escalation authority")
        block.append("       - Define documented resolution workflow")
        return block

    # ----------------------------------------------------
    # SCORE 4 → Controlled (targets, audit enforcement, SLA)
    # ----------------------------------------------------
    if score == 4:
        block.append("   7.1 Performance Monitoring Framework")
        block.append("       - Define KPI formula and calculation method")
        block.append("       - Define target values and tolerance thresholds")
        block.append("       - Define alert and breach triggers")
        block.append("       - Define corrective action activation criteria")
        block.append("   7.2 Compliance and Audit Verification")
        block.append("       - Define audit sampling methodology")
        block.append("       - Define validation frequency")
        block.append("       - Define evidence retention requirements")
        block.append("       - Align with Internal Audit Function oversight")
        block.append("   7.3 Controlled Escalation Model")
        block.append("       - Define formal SLA timelines for issue resolution")
        block.append("       - Define mandatory reporting to Data Governance Council")
        block.append("       - Define accountability tracking mechanism")
        return block

    # ----------------------------------------------------
    # SCORE 5 → Optimized (automation + multi-cycle evidence)
    # ----------------------------------------------------
    if score == 5:
        block.append("   7.1 Automated Performance Monitoring")
        block.append("       - Define automated KPI data capture mechanisms")
        block.append("       - Define automated threshold enforcement")
        block.append("       - Define automated alerting and exception logging")
        block.append("   7.2 Continuous Compliance and Adaptive Governance")
        block.append("       - Define multi-cycle trend analysis requirements")
        block.append("       - Define root cause clustering and preventive redesign triggers")
        block.append("       - Embed audit integration within governance operating model")
        block.append("   7.3 Strategic Escalation Optimization")
        block.append("       - Define data-driven escalation prioritization")
        block.append("       - Define decision optimization mechanisms")
        block.append("   7.4 Evidence of Optimization and Institutionalization")
        block.append("       7.4.1 Quantitative multi-cycle performance improvement evidence")
        block.append("       7.4.2 Before vs After KPI comparative metrics")
        block.append("       7.4.3 Governance automation proof points")
        block.append("       7.4.4 External benchmark alignment reference")
        block.append("       7.4.5 Documented governance operating model integration")
        return block

    return block


# ---------------------------------------------------------
# 3. Enforce maturity language discipline
# ---------------------------------------------------------

def _enforce_maturity_language(text: str, score: int) -> str:
    """
    Remove KPI language below Score 3.
    """
    if score < 3:
        text = re.sub(r'.*KPI.*\n?', '', text)
        text = re.sub(r'.*performance indicator.*\n?', '', text, flags=re.IGNORECASE)

    return text


# ---------------------------------------------------------
# 4. Clean forbidden placeholders
# ---------------------------------------------------------

def _remove_forbidden_placeholders(text: str) -> str:
    forbidden = [
        "Not applicable",
        "N/A",
        "Only applicable if Score = 5"
    ]

    for f in forbidden:
        text = text.replace(f, "")

    return text


# ---------------------------------------------------------
# 5. Normalize spacing
# ---------------------------------------------------------

def _normalize_spacing(text: str) -> str:
    lines = text.splitlines()
    cleaned = []
    previous_blank = False

    for line in lines:
        if not line.strip():
            if not previous_blank:
                cleaned.append("")
            previous_blank = True
        else:
            cleaned.append(line.rstrip())
            previous_blank = False

    return "\n".join(cleaned).strip()

# =========================================================
# Dynamic Score by action code
# =========================================================

def _build_dynamic_score_map(items):
    from collections import defaultdict

    domain_actions = defaultdict(set)

    # Coleta action codes distintos por domínio
    for it in items:
        domain = it.get("domain")
        action = it.get("action_code")
        if domain and action:
            domain_actions[domain].add(action)

    score_map = {}

    for domain, actions in domain_actions.items():

        # Ordena pelo número das duas últimas posições
        ordered = sorted(actions, key=lambda x: int(x[-2:]))

        # Score = posição ordinal
        for idx, action in enumerate(ordered):
            score_map[(domain, action)] = idx

    return score_map

# =========================================================
# MAIN PATCH FUNCTION
# =========================================================

def apply_governance_patches(domain: str):

    domain = domain.upper().strip()
    input_path = OUTPUT_DIR / f"{domain}_theory_demo_output.json"
    output_path = OUTPUT_DIR / f"{domain}_theory_demo_output_PATCHED.json"

    if not input_path.exists():
        raise FileNotFoundError(f"Missing demo output: {input_path}")

    data = load_json(input_path, default={})
    items = data.get("items", [])

    # 🔥 Construção dinâmica do score
    score_map = _build_dynamic_score_map(items)

    patched_items = []    
    
    for item in items:
        demo_text = item.get("demo", "")
        action_code = item.get("action_code", "")
        domain_name = item.get("domain")

        # 🔥 Score dinâmico por domínio
        score = score_map.get((domain_name, action_code), 0)

        demo_text = _fix_duplicated_terms(demo_text)
        demo_text = _rebuild_section_7(demo_text, score)
        demo_text = _enforce_maturity_language(demo_text, score)
        demo_text = _remove_forbidden_placeholders(demo_text)
        demo_text = _normalize_spacing(demo_text)

        patched_items.append({
            "domain": domain_name,
            "action_code": action_code,
            "procedure": item.get("procedure"),
            "demo": demo_text
        })

    save_json(output_path, {"items": patched_items})
    log(f"PATCH saved: {output_path}")

# =========================================================
# Main
# =========================================================

def main():
    parser = argparse.ArgumentParser(description="DOMMx Demo Generator")
    parser.add_argument("--mode", choices=["all", "domain"], default="domain")
    parser.add_argument("--domain", help="Domain acronym (e.g. DG)")
    parser.add_argument("--patch", action="store_true")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-workers", type=int, default=DEFAULT_MAX_WORKERS)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--clear-cache", action="store_true")

    args = parser.parse_args()

    if args.mode == "domain":
        if not args.domain:
            raise ValueError("Domain required")
        domains = [args.domain.upper()]
    else:
        files = list(OUTPUT_DIR.glob("*_theory_demo_output.json"))
        domains = [f.name.split("_")[0] for f in files]

    for dom in domains:
        if args.patch:
            log(f"Patching domain {dom}")
            apply_governance_patches(dom)
        else:
            log(f"Generating domain {dom}")
            run_domain(dom, args.model, args.max_workers,
                       args.batch_size, args.clear_cache)

    log("Done")


if __name__ == "__main__":
    main()