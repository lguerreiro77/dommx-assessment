import uuid
from datetime import datetime
from storage.google_sheets import get_sheet
import streamlit as st

@st.cache_data(ttl=30,show_spinner=False)
def get_projects_cached():
    sheet = get_sheet("projects")
    return sheet.get_all_records()

def get_projects():
    return get_projects_cached()



def create_project(name, created_by):
    sheet = get_sheet("projects")

    sheet.append_row([
        str(uuid.uuid4()),
        name,
        created_by,
        datetime.utcnow().isoformat(),
        True
    ])


def update_project(project_id, name, is_active):
    sheet = get_sheet("projects")
    rows = sheet.get_all_records()

    for i, r in enumerate(rows, start=2):
        if r.get("project_id") == project_id:
            sheet.update(
                f"B{i}:E{i}",
                [[
                    name,
                    r.get("created_by"),
                    datetime.utcnow().isoformat(),
                    is_active
                ]]
            )
            break


def delete_project(project_id):
    sheet = get_sheet("projects")
    rows = sheet.get_all_records()

    for i, r in enumerate(rows, start=2):
        if r.get("project_id") == project_id:
            sheet.delete_rows(i)
            break
            
def get_all_projects():
    sheet = get_sheet("projects")
    return sheet.get_all_records()            
