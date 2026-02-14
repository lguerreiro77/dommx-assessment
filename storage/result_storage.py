import os
import json
from core.config import BASE_DIR

RESULTS_DIR = os.path.join(BASE_DIR, "data/results")
os.makedirs(RESULTS_DIR, exist_ok=True)

def result_path(user_id):
    return os.path.join(RESULTS_DIR, f"{user_id}.json")

def save_results(user_id, payload):
    with open(result_path(user_id), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

def load_results(user_id):
    path = result_path(user_id)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
