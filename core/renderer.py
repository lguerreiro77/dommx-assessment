import streamlit as st
import yaml

from core.renderer_init import initialize_renderer
from core.renderer_controller import handle_page_and_dialogs
from core.renderer_assessment import render_assessment
from core.config import BASE_DIR, resolve_path


def render_app():
       
    try:
        
        # 🔹 Carregar orchestration exatamente igual ao assessment
        fs_path = resolve_path(BASE_DIR, "FileSystem_Setup.yaml")
        with open(fs_path, "r", encoding="utf-8") as f:
            fs_setup = yaml.safe_load(f) or {}

        config = (fs_setup.get("orchestrator_config") or {})
        orch_path = resolve_path(
            BASE_DIR,
            config.get("main_orchestration", "default_execution.yaml")
        )

        with open(orch_path, "r", encoding="utf-8") as f:
            orch = yaml.safe_load(f) or {}

        req_list = orch.get("execution_request", []) or []

        # 🔹 AGORA PASSA req_list corretamente
        initialize_renderer()

        # controla account + modais
        if handle_page_and_dialogs():
            return

        # roda assessment principal
        render_assessment()

    except Exception as e:
        from core.flow_engine import add_message
        add_message(f"Renderer error: {e}", "error")
        st.exception(e)
