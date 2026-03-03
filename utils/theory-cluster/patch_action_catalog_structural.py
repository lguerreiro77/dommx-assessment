import yaml
import argparse
import re
from pathlib import Path

# ==========================================================
# BASE PATHS (alinhado com theory_cluster.py)
# ==========================================================

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
GENERAL_DIR = DATA_DIR / "general"
FLOW_PATH = GENERAL_DIR / "flow.yaml"
DOMAINS_DIR = DATA_DIR / "domains"

DEFAULT_LANGUAGE = "us"

# ==========================================================
# PROCEDURE LIBRARY (editável)
# ==========================================================

PROCEDURE_LIBRARY = {
    "04": {
        "number": 6,
        "name": "Structural Institutionalization Reinforcement",
        "prerequisite": "Requires approved governance mechanism and formalized policy baseline",
        "deliverable": "Institutionalized governance procedure with assigned control owner and documented evidence of repeatable execution",
        "recommendations": [
            "Assign a formally accountable Control Owner responsible for sustaining the governance mechanism.",
            "Define objective acceptance criteria confirming stable and consistent execution.",
            "Produce documented artefacts evidencing repeatable operational application.",
            "Ensure integration into established organizational routines.",
            "Maintain traceability between the governance mechanism and governing policy."
        ]
    },
    "06": {
        "number": 6,
        "name": "Structural Measurement and Oversight Reinforcement",
        "prerequisite": "Requires institutionalized governance mechanism",
        "deliverable": "Managed and measured governance control environment",
        "recommendations": [
            "Define measurable performance metrics aligned with governance objectives.",
            "Implement structured monitoring mechanisms or dashboards.",
            "Establish formal validation cycles including periodic reviews.",
            "Maintain traceable documentation of performance results.",
            "Define escalation pathways for unresolved deviations."
        ]
    },
    "09": {
        "number": 6,
        "name": "Structural Optimization and Adaptive Reinforcement",
        "prerequisite": "Requires managed and measured governance mechanism",
        "deliverable": "Optimized governance process demonstrating automation and adaptive improvement",
        "recommendations": [
            "Introduce automation elements supporting enforcement and monitoring.",
            "Implement continuous improvement loops based on performance trends.",
            "Conduct benchmarking against recognized governance frameworks.",
            "Document measurable multi-cycle improvement.",
            "Ensure adaptability to regulatory and organizational change."
        ]
    }
}

# ==========================================================
# HELPERS
# ==========================================================

def load_yaml(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def save_yaml(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, sort_keys=False, allow_unicode=True)

def extract_suffix(action_code: str):
    match = re.search(r'-(\d{2})$', action_code)
    return match.group(1) if match else None

def procedure_exists(action_block):
    for p in action_block.get("procedures", []):
        if p.get("number") == 6:
            return True
    return False

# ==========================================================
# FLOW HANDLING
# ==========================================================

def get_flow_domains():
    flow = load_yaml(FLOW_PATH)
    items = flow.get("Domain_flow") or []
    items = sorted(items, key=lambda x: int(x.get("sequence", 9999)))
    return items

def select_domains(flow_items, domain_filter):
    if not domain_filter:
        return flow_items
    wanted = domain_filter.upper().strip()
    return [
        d for d in flow_items
        if str(d.get("acronym", "")).upper().strip() == wanted
    ]

def resolve_action_catalog_path(language, flow_item):
    files = flow_item.get("files") or {}
    ac_file = files.get("action_catalog")
    if not ac_file:
        raise ValueError(f"No action_catalog file in flow for {flow_item}")
    return DOMAINS_DIR / language / ac_file

# ==========================================================
# PATCH ENGINE
# ==========================================================

def patch_catalog(ac_path: Path, overwrite=False):

    data = load_yaml(ac_path)
    catalog = data.get("action_catalog")

    if not isinstance(catalog, dict):
        print(f"Skipping {ac_path.name} (invalid structure)")
        return

    sorted_keys = sorted(
        catalog.keys(),
        key=lambda x: int(extract_suffix(x) or 0)
    )

    changes = 0

    for code in sorted_keys:
        suffix = extract_suffix(code)
        if suffix in PROCEDURE_LIBRARY:
            action_block = catalog[code]
            if not procedure_exists(action_block):
                action_block.setdefault("procedures", []).append(
                    PROCEDURE_LIBRARY[suffix]
                )
                print(f"✔ Added Procedure 6 to {code}")
                changes += 1
            else:
                print(f"• Already present in {code}")

    if changes == 0:
        print(f"No changes needed in {ac_path.name}")
        return

    if overwrite:
        save_yaml(ac_path, data)
        print(f"Saved (overwrite): {ac_path}")
    else:
        patched_path = ac_path.with_name(ac_path.stem + "_PATCHED.yaml")
        save_yaml(patched_path, data)
        print(f"Saved: {patched_path}")

# ==========================================================
# MAIN
# ==========================================================

def main():

    parser = argparse.ArgumentParser(description="Patch Action Catalog Structural Procedure 6 via flow.yaml")
    parser.add_argument("--language", default=DEFAULT_LANGUAGE)
    parser.add_argument("--domain", default=None)
    parser.add_argument("--overwrite", action="store_true")

    args = parser.parse_args()

    flow_items = get_flow_domains()
    selected = select_domains(flow_items, args.domain)

    if not selected:
        raise ValueError("No domains selected")

    print(f"Mode: {'ALL' if not args.domain else args.domain.upper()}")

    for domain_item in selected:
        acronym = domain_item.get("acronym")
        print(f"\nProcessing {acronym}...")
        ac_path = resolve_action_catalog_path(args.language, domain_item)

        if not ac_path.exists():
            print(f"Missing file: {ac_path}")
            continue

        patch_catalog(ac_path, overwrite=args.overwrite)


if __name__ == "__main__":
    main()