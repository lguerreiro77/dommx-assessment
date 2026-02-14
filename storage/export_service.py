import os
import json
import pandas as pd
from core.config import BASE_DIR
from storage.user_storage import load_user

RESULTS_DIR = os.path.join(BASE_DIR, "data", "results")
EXPORT_FILE = os.path.join(BASE_DIR, "data", "results_final.xlsx")


def export_all_to_excel():

    rows = []

    for file in os.listdir(RESULTS_DIR):

        if not file.endswith(".json"):
            continue

        user_id = file.replace(".json", "")
        path = os.path.join(RESULTS_DIR, file)

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        user = load_user(user_id)
        email = user.get("email") if user else ""

        row = {
            "user_id": user_id,
            "email": email,
            **data.get("answers", {})
        }

        rows.append(row)

    if rows:
        df = pd.DataFrame(rows)
        df.to_excel(EXPORT_FILE, index=False)

    return EXPORT_FILE
