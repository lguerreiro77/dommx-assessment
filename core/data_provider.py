import streamlit as st
from storage.project_storage import get_all_projects
from storage.user_project_storage import get_user_project_links


@st.cache_data(show_spinner=False)
def load_projects_for_user(user_id: str):
    """
    Carrega projetos do usuário.
    1 leitura por worksheet.
    Cacheado.
    """

    if not user_id:
        return []

    # 1 leitura
    all_projects = get_all_projects()

    # 1 leitura
    links = get_user_project_links()

    user_links = [
        link for link in links
        if str(link.get("user_id")) == str(user_id)
    ]

    project_ids = {str(l.get("project_id")) for l in user_links}

    projects = [
        p for p in all_projects
        if str(p.get("id")) in project_ids
    ]

    return projects


def clear_projects_cache():
    load_projects_for_user.clear()
