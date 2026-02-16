import streamlit as st
from datetime import datetime
from storage.google_sheets import get_sheet


@st.cache_data(ttl=60, show_spinner=False)
def get_projects_for_user(user_id: str):
    sheet = get_sheet("usersprojects")
    rows = sheet.get_all_records()
    return [r.get("project_id") for r in rows if str(r.get("user_id", "")).strip() == str(user_id).strip()]


@st.cache_data(ttl=60, show_spinner=False)
def get_all_user_projects():
    sheet = get_sheet("usersprojects")
    return sheet.get_all_records()


def associate_users_projects(user_ids: list, project_ids: list, created_by: str):
    sheet = get_sheet("usersprojects")

    # leitura única, ainda necessária para dedupe, mas cacheada não é confiável para evitar duplicado
    rows = sheet.get_all_records()
    existing = {(str(r.get("user_id", "")).strip(), str(r.get("project_id", "")).strip()) for r in rows}

    now = datetime.utcnow().isoformat()
    rows_to_add = []

    for user_id in user_ids:
        for project_id in project_ids:
            key = (str(user_id).strip(), str(project_id).strip())
            if key not in existing:
                rows_to_add.append([key[0], key[1], now, created_by])

    if rows_to_add:
        sheet.append_rows(rows_to_add)

    get_all_user_projects.clear()
    get_projects_for_user.clear()


def remove_user_project_association(user_id: str, project_id: str):
    sheet = get_sheet("usersprojects")
    rows = sheet.get_all_records()

    uid = str(user_id).strip()
    pid = str(project_id).strip()

    for idx, row in enumerate(rows, start=2):
        if str(row.get("user_id", "")).strip() == uid and str(row.get("project_id", "")).strip() == pid:
            sheet.delete_rows(idx)
            break

    get_all_user_projects.clear()
    get_projects_for_user.clear()
