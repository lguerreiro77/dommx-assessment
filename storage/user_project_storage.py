import streamlit as st
from datetime import datetime

from data.repository_factory import get_repository

repo = get_repository()


@st.cache_data(ttl=60, show_spinner=False)
def get_projects_for_user(user_id: str):
    rows = repo.fetch_all("usersprojects")

    uid = str(user_id).strip()

    return [
        r.get("project_id")
        for r in rows
        if str(r.get("user_id", "")).strip() == uid
    ]


@st.cache_data(ttl=60, show_spinner=False)
def get_all_user_projects():
    return repo.fetch_all("usersprojects")


def associate_users_projects(user_ids: list, project_ids: list, created_by: str):

    rows = repo.fetch_all("usersprojects")

    existing = {
        (
            str(r.get("user_id", "")).strip(),
            str(r.get("project_id", "")).strip()
        )
        for r in rows
    }

    now = datetime.utcnow().isoformat()

    for user_id in user_ids:
        for project_id in project_ids:

            uid = str(user_id).strip()
            pid = str(project_id).strip()

            key = (uid, pid)

            if key not in existing:

                repo.insert(
                    "usersprojects",
                    {
                        "user_id": uid,
                        "project_id": pid,
                        "created_at": now,
                        "created_by": created_by
                    }
                )

    get_all_user_projects.clear()
    get_projects_for_user.clear()


def remove_user_project_association(user_id: str, project_id: str):

    repo.delete(
        "usersprojects",
        {
            "user_id": str(user_id).strip(),
            "project_id": str(project_id).strip()
        }
    )

    get_all_user_projects.clear()
    get_projects_for_user.clear()
