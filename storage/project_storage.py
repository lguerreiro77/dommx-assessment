import uuid
from datetime import datetime
import streamlit as st

from data.repository_factory import get_repository

repo = get_repository()


@st.cache_data(ttl=60, show_spinner=False)
def get_projects():
    return repo.fetch_all("projects")


def get_all_projects():
    return get_projects()


def create_project(name, created_by, allow_open_access=False):
    project_id = str(uuid.uuid4())
    timestamp = datetime.utcnow().isoformat()

    repo.insert("projects", {
        "project_id": project_id,
        "name": name,
        "created_at": timestamp,
        "created_by": created_by,
        "is_active": True,
        "allow_open_access": allow_open_access,
    })

    get_projects.clear()


def update_project(project_id, name, is_active, allow_open_access):
    repo.update(
        "projects",
        {"project_id": project_id},
        {
            "name": name,
            "is_active": is_active,
            "allow_open_access": allow_open_access,
        }
    )

    get_projects.clear()


def delete_project(project_id):
    repo.delete(
        "projects",
        {"project_id": project_id}
    )

    get_projects.clear()
