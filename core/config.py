import os
import yaml
import streamlit as st

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# -------------------------------------------------
# DEFAULT GLOBALS (DEVEM EXISTIR ANTES DE IMPORT)
# -------------------------------------------------

app_config = {}

APP_TITLE = "🛡️ DOMMx Technical Diagnostic"
SHOW_INTRO = True
INTRO_HEADING = "Welcome"
INTRO_MESSAGE = ""

# -------------------------------------------------
# HELPERS
# -------------------------------------------------

def resolve_path(base_dir, relative_path):
    if not relative_path:
        return None

    p = str(relative_path).strip()
    if not p:
        return None

    # 1) absoluto
    if os.path.isabs(p):
        return p if os.path.exists(p) else None

    # normaliza separadores
    p_norm = p.replace("\\", "/")

    # 2) paths globais do projeto (ex: data/general/..., data/projects/...)
    if p_norm.startswith("data/"):
        candidate = os.path.join(BASE_DIR, p_norm.replace("/", os.sep))
        return candidate if os.path.exists(candidate) else None

    # 3) relativo ao base_dir
    candidate = os.path.join(base_dir, p)
    return candidate if os.path.exists(candidate) else None



def safe_load(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def get_project_root():
    return st.session_state.get("project_root")


def get_general_dir():
    import os
    import streamlit as st

    active_project = st.session_state.get("active_project")

    if active_project:
        project_general = os.path.join(
            BASE_DIR,
            "data",
            "projects",
            str(active_project),
            "General"
        )

        if os.path.isdir(project_general):
            return project_general

    # fallback legacy
    return os.path.join(BASE_DIR, "data", "general")



def get_filesystem_setup_path():
    import os
    import streamlit as st

    active_project = st.session_state.get("active_project")

    if active_project:
        project_fs = os.path.join(
            BASE_DIR,
            "data",
            "projects",
            str(active_project),
            "General",
            "FileSystem_Setup.yaml"
        )

        if os.path.isfile(project_fs):
            return project_fs

    # fallback legacy
    return os.path.join(BASE_DIR, "filesystem_setup.yaml")



def refresh_runtime_config():
    global app_config, APP_TITLE, SHOW_INTRO, INTRO_HEADING, INTRO_MESSAGE

    general_dir = get_general_dir()
    app_cfg_path = os.path.join(general_dir, "app_config.yaml")

    loaded = safe_load(app_cfg_path) or {}
    app_config = loaded

    APP_TITLE = app_config.get("app", {}).get(
        "title", "🛡️ DOMMx Technical Diagnostic"
    )
    SHOW_INTRO = app_config.get("app", {}).get("show_intro", True)
    INTRO_HEADING = app_config.get("intro", {}).get("heading", "Welcome")
    INTRO_MESSAGE = app_config.get("intro", {}).get("message", "")


# Inicializa config padrão
refresh_runtime_config()
