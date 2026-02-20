import os
import shutil
import uuid
from datetime import datetime
import streamlit as st

import stat
import time

from core.config import BASE_DIR
from data.repository_factory import get_repository

repo = get_repository()


@st.cache_data(ttl=60, show_spinner=False)
def get_projects():
    return repo.fetch_all("projects")


def get_all_projects():
    return get_projects()


def _copy_dir_contents(src_dir: str, dst_dir: str) -> None:
    if not os.path.isdir(src_dir):
        return

    os.makedirs(dst_dir, exist_ok=True)

    for item in os.listdir(src_dir):
        s = os.path.join(src_dir, item)
        d = os.path.join(dst_dir, item)

        if os.path.isdir(s):
            shutil.copytree(s, d, dirs_exist_ok=True)
        else:
            shutil.copy2(s, d)


def create_project(name, created_by, allow_open_access=False):
    project_id = str(uuid.uuid4())
    timestamp = datetime.utcnow().isoformat()

    # FIX: tabela projects usa last_update_timestamp (não created_at)
    repo.insert("projects", {
        "project_id": project_id,
        "name": name,
        "created_by": created_by,
        "last_update_timestamp": timestamp,
        "is_active": True,
        "allow_open_access": allow_open_access,
    })

    # -----------------------------
    # MULTI-TENANT FILESYSTEM SETUP
    # -----------------------------
    project_root = os.path.join(BASE_DIR, "data", "projects", project_id)
    domains_dest = os.path.join(project_root, "Domains")
    general_dest = os.path.join(project_root, "General")

    # fontes (baseline)
    domains_src = os.path.join(BASE_DIR, "data", "domains", "language", "default")
    general_src = os.path.join(BASE_DIR, "data", "general")

    # filesystem setup no root do repo
    fs_repo_root_src = os.path.join(BASE_DIR, "filesystem_setup.yaml")

    os.makedirs(domains_dest, exist_ok=True)
    os.makedirs(general_dest, exist_ok=True)

    _copy_dir_contents(domains_src, domains_dest)
    _copy_dir_contents(general_src, general_dest)

    # copiar filesystem_setup.yaml para:
    # 1) raiz do projeto
    # 2) General do projeto (este será o ativo)
    if os.path.isfile(fs_repo_root_src):
        shutil.copy2(fs_repo_root_src, os.path.join(project_root, "FileSystem_Setup.yaml"))
        shutil.copy2(fs_repo_root_src, os.path.join(general_dest, "FileSystem_Setup.yaml"))

    get_projects.clear()
    return project_id


def update_project(project_id, name, is_active, allow_open_access):
    timestamp = datetime.utcnow().isoformat()

    repo.update(
        "projects",
        {"project_id": project_id},
        {
            "name": name,
            "is_active": is_active,
            "allow_open_access": allow_open_access,
            "last_update_timestamp": timestamp,
        }
    )

    get_projects.clear()


def delete_project(project_id):
    project_id = str(project_id).strip()

    # -----------------------------
    # Se projeto ativo → limpar state COMPLETO
    # -----------------------------
    if st.session_state.get("active_project") == project_id:
        st.session_state.active_project = None
        st.session_state.project_root = None

    # Remove dependências primeiro
    tables_with_project_id = [
        "results",
        "usersprojects",
        "finished_assessments",
        "logs",
    ]

    for table in tables_with_project_id:
        try:
            repo.delete(table, {"project_id": project_id})
        except Exception:
            pass

    # Remove projeto da tabela
    repo.delete("projects", {"project_id": project_id})

    # Limpa cache antes de checar restante
    get_projects.clear()

    # -----------------------------
    # MULTI-TENANT FILESYSTEM TEARDOWN
    # -----------------------------
    project_root = os.path.join(BASE_DIR, "data", "projects", project_id)

    if os.path.isdir(project_root):
        
        def remove_readonly(func, path, _):
            os.chmod(path, stat.S_IWRITE)
            func(path)

        for attempt in range(10):
            try:
                shutil.rmtree(project_root, onerror=remove_readonly)
                break
            except Exception as e:
                print(f"DELETE ATTEMPT {attempt + 1} FAILED:", e)
                time.sleep(0.5)

  