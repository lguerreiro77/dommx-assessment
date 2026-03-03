# =========================================================
# tree_action_cluster.py
# Gera JSON estrutural completo da árvore (decision_tree + action_catalog)
# Apenas estrutura — sem IA, sem cache
# =========================================================

import json
import yaml
import argparse
from pathlib import Path
from datetime import datetime


# =========================================================
# BASE DIR (mesmo padrão do theory_cluster.py)
# =========================================================

BASE_DIR = Path(__file__).resolve().parent.parent.parent

DATA_DIR = BASE_DIR / "data"
GENERAL_DIR = DATA_DIR / "general"
FLOW_PATH = GENERAL_DIR / "flow.yaml"

DOMAINS_DIR = DATA_DIR / "domains"

THEORY_DIR = BASE_DIR / "utils" / "theory-cluster"
OUTPUT_DIR = THEORY_DIR / "tree_output" / "xcopy"

OUTPUT_DIR = THEORY_DIR / "tree_output" / "original"
IMPROVED_DIR = THEORY_DIR / "tree_output" / "improved"


# =========================================================
# HELPERS
# =========================================================

def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)


def load_yaml(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_json(path: Path, obj):
    ensure_dir(path.parent)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


# =========================================================
# FLOW
# =========================================================

def get_flow_domains():
    flow = load_yaml(FLOW_PATH)
    items = flow.get("Domain_flow", [])
    items = sorted(items, key=lambda x: int(x.get("sequence", 9999)))
    return items


def resolve_yaml_paths(language, domain_item):
    files = domain_item.get("files", {})
    dt_file = files.get("decision_tree")
    ac_file = files.get("action_catalog")

    dt_path = DOMAINS_DIR / language / dt_file
    ac_path = DOMAINS_DIR / language / ac_file

    return dt_path, ac_path


# =========================================================
# BUILD STRUCTURE
# =========================================================

def build_domain_tree(domain_item, language):

    acronym = domain_item.get("acronym")
    name = domain_item.get("name")
    sequence = domain_item.get("sequence")

    dt_path, ac_path = resolve_yaml_paths(language, domain_item)

    if not dt_path.exists():
        raise FileNotFoundError(f"Decision tree not found: {dt_path}")

    if not ac_path.exists():
        raise FileNotFoundError(f"Action catalog not found: {ac_path}")

    dt_yaml = load_yaml(dt_path)
    ac_yaml = load_yaml(ac_path)

    questions = (
        dt_yaml.get("questions")
        or dt_yaml.get("decision_tree", {}).get("questions")
        or {}
    )

    catalog_root = (
        ac_yaml.get("action_catalog")
        or ac_yaml.get("ActionCatalog")
        or {}
    )

    tree = {
        "domain": {
            "acronym": acronym,
            "name": name,
            "sequence": sequence
        },
        "decision_tree": [],
        "action_catalog": catalog_root,
        "generated_at_utc": datetime.utcnow().isoformat()
    }

    for q_id, q_data in questions.items():

        explanation = q_data.get("explanation")
        objective = q_data.get("objective")

        score_map = q_data.get("score_action_mapping", {})

        question_node = {
            "question_id": q_id,
            "explanation": explanation,
            "objective": objective,
            "scores": []
        }

        for score, mapping in score_map.items():

            action_code = mapping.get("action_code")
            action_desc = mapping.get("description")

            action_payload = catalog_root.get(action_code)

            question_node["scores"].append({
                "score": score,
                "action_code": action_code,
                "action_description": action_desc,
                "action": action_payload
            })

        tree["decision_tree"].append(question_node)

    return tree


# =========================================================
# MAIN
# =========================================================

def main():

    parser = argparse.ArgumentParser(
        description="Generate structural tree JSON per domain"
    )

    parser.add_argument(
        "--language",
        default="us",
        help="Language folder under data/domains (default: us)"
    )

    parser.add_argument(
        "--domain",
        default=None,
        help="Domain acronym (e.g., DG) or multiple separated by comma (e.g., DG,DQ). If omitted, run all domains."
    )

    args = parser.parse_args()

    ensure_dir(OUTPUT_DIR)

    flow_items = get_flow_domains()

    # -------------------------------------------------
    # DOMAIN FILTER
    # -------------------------------------------------

    if args.domain:

        requested = [
            d.strip().upper()
            for d in args.domain.split(",")
            if d.strip()
        ]

        selected = [
            d for d in flow_items
            if d.get("acronym", "").upper() in requested
        ]

        missing = set(requested) - {
            d.get("acronym", "").upper() for d in selected
        }

        if missing:
            raise ValueError(f"Invalid domain(s): {missing}")

    else:
        selected = flow_items  # default = ALL

    if not selected:
        raise ValueError("No domains selected")

    print(f"Running domains: {[d.get('acronym') for d in selected]}")

    # -------------------------------------------------
    # EXECUTION
    # -------------------------------------------------

    for domain_item in selected:

        acronym = domain_item.get("acronym")

        print(f"Generating tree for domain {acronym}...")

        tree_obj = build_domain_tree(domain_item, args.language)

        out_path = OUTPUT_DIR / f"{acronym}_tree_action_cluster.json"
        save_json(out_path, tree_obj)

        print(f"Saved: {out_path}")
        

if __name__ == "__main__":
    main()
