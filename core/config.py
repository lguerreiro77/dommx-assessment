import os
import yaml

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def resolve_path(base_dir, relative_path):
    candidate = os.path.join(base_dir, relative_path)

    if os.path.exists(candidate):
        return candidate

    # tentativa case-insensitive
    for root, dirs, files in os.walk(base_dir):
        for f in files:
            if f.lower() == os.path.basename(relative_path).lower():
                return os.path.join(root, f)

    return None

def safe_load(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except:
        return None

app_config = safe_load(os.path.join(BASE_DIR, "data/general/app_config.yaml")) or {}

APP_TITLE = app_config.get("app", {}).get(
    "title", "🛡️ DOMMx Technical Diagnostic"
)

SHOW_INTRO = app_config.get("app", {}).get("show_intro", True)
INTRO_HEADING = app_config.get("intro", {}).get("heading", "Welcome")
INTRO_MESSAGE = app_config.get("intro", {}).get("message", "")
