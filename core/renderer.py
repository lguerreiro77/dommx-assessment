import streamlit as st
import yaml
import os

from core.renderer_init import initialize_renderer
from core.renderer_controller import handle_page_and_dialogs
from core.renderer_assessment import render_assessment
from core.config import BASE_DIR, resolve_path, get_filesystem_setup_path, get_general_dir


@st.cache_data(show_spinner=False)
def load_yaml_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
        

def render_app():
    
    
    if st.session_state.get("bootstrap_recovery"):
        st.warning(
            "Project structure not found.\n\n"
            "Create project structure and configuration.\n"
            "This applies even to existing database projects."
        )
        st.session_state.bootstrap_recovery = False

    if not st.session_state.get("active_project"):
        return
        
       
    try:
        
        # 🔹 Carregar orchestration exatamente igual ao assessment
        active_project = st.session_state.get("active_project")

        project_root = None
        project_general = None
        project_domains = None

        if active_project:
            project_root = os.path.join(BASE_DIR, "data", "projects", str(active_project))
            project_general = os.path.join(project_root, "general")
            project_domains = os.path.join(project_root, "domains")

        # -------------------------------------------------
        # LOAD FILESYSTEM SETUP
        # -------------------------------------------------
        fs_path = None

        if project_general and os.path.isfile(os.path.join(project_general, "FileSystem_Setup.yaml")):
            fs_path = os.path.join(project_general, "FileSystem_Setup.yaml")
        else:
            fs_path = os.path.join(BASE_DIR, "filesystem_setup.yaml")

        if not os.path.isfile(fs_path):
            st.error("Filesystem setup file not found.")
            st.stop()

        fs_setup = load_yaml_file(fs_path)

        # -------------------------------------------------
        # ORCHESTRATION
        # -------------------------------------------------
        orch_filename = fs_setup.get("orchestrator_config", {}).get(
            "main_orchestration",
            "data/general/default_execution.yaml"
        )

        if project_general and os.path.isfile(os.path.join(project_general, "default_execution.yaml")):
            orch_path = os.path.join(project_general, "default_execution.yaml")
        else:
            orch_path = os.path.join(BASE_DIR, "data", orch_filename)

        if not os.path.isfile(orch_path):
            st.error("Orchestration file not found.")
            st.stop()

        orch = load_yaml_file(orch_path)

        # -------------------------------------------------
        # FLOW
        # -------------------------------------------------
        flow_filename = fs_setup.get("orchestrator_config", {}).get(
            "main_flow",
            "data/general/flow.yaml"
        )

        if project_general and os.path.isfile(os.path.join(project_general, "flow.yaml")):
            flow_path = os.path.join(project_general, "flow.yaml")
        else:
            flow_path = os.path.join(BASE_DIR, "data", flow_filename)

        if not os.path.isfile(flow_path):
            st.error("Flow file not found.")
            st.stop()

        flow = load_yaml_file(flow_path)

        st.session_state._flow = flow
        
        # -------------------------------------------------
        # domains ROOT
        # -------------------------------------------------
        if project_domains and os.path.isdir(project_domains):
            domain_root = project_domains
        else:
            st.error("Project domain structure not found.")
            st.stop()

        req_list = orch.get("execution_request", []) or []
        
        st.session_state.execution_request = req_list            

        # 🔹 AGORA PASSA req_list corretamente
        initialize_renderer()       
               
        # controla account + modais
        if handle_page_and_dialogs():
            return

        st.session_state._orch = orch
        st.session_state._flow = flow
        st.session_state._domain_root = domain_root
        
        # roda assessment principal
        render_assessment()
        
        

    except Exception as e:
        from core.flow_engine import add_message
        add_message(f"Renderer error: {e}", "error")
        st.exception(e)

    