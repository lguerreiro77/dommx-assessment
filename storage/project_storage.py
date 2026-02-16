import uuid
from datetime import datetime
import streamlit as st
from storage.google_sheets import get_sheet, get_spreadsheet


@st.cache_data(ttl=60, show_spinner=False)
def get_projects():
    sheet = get_sheet("projects")
    return sheet.get_all_records()


def get_all_projects():
    return get_projects()


def create_project(name, created_by, allow_open_access=False):
    sheet = get_spreadsheet().worksheet("projects")

    project_id = str(uuid.uuid4())
    timestamp = datetime.utcnow().isoformat()

    sheet.append_row([
        project_id,
        name,
        timestamp,
        created_by,
        True,
        allow_open_access
    ])

    get_projects.clear()


def update_project(project_id, name, is_active, allow_open_access):
    sheet = get_spreadsheet().worksheet("projects")
    rows = get_projects()  # usa cache para localizar linha, reduz leitura repetida

    for idx, row in enumerate(rows, start=2):
        if row.get("project_id") == project_id:
            sheet.update(f"B{idx}", [[name]])
            sheet.update(f"E{idx}", [[is_active]])
            sheet.update(f"F{idx}", [[allow_open_access]])
            break

    get_projects.clear()


def delete_project(project_id):
    sheet = get_sheet("projects")
    rows = get_projects()

    for i, r in enumerate(rows, start=2):
        if str(r.get("project_id", "")).strip() == str(project_id).strip():
            sheet.delete_rows(i)
            break

    get_projects.clear()
