import uuid
from datetime import datetime
from storage.google_sheets import get_sheet
from storage.google_sheets import get_spreadsheet
import streamlit as st

#@st.cache_data(ttl=30,show_spinner=False)

def get_projects_cached():
    sheet = get_sheet("projects")
    return sheet.get_all_records()

def get_projects():
    return get_projects_cached()



def create_project(name, created_by, allow_open_access=False):
    sheet = get_spreadsheet().worksheet("projects")
    sheet.append_row([
        generate_project_id(),
        name,
        current_timestamp(),
        created_by,
        True,
        allow_open_access
    ])


def update_project(project_id, name, is_active, allow_open_access):
    sheet = get_spreadsheet().worksheet("projects")
    rows = sheet.get_all_records()

    for idx, row in enumerate(rows, start=2):
        if row["project_id"] == project_id:

            sheet.update(f"B{idx}", [[name]])
            sheet.update(f"E{idx}", [[is_active]])
            sheet.update(f"F{idx}", [[allow_open_access]])

            break



def delete_project(project_id):
    sheet = get_sheet("projects")
    rows = sheet.get_all_records()

    for i, r in enumerate(rows, start=2):
        if r.get("project_id") == project_id:
            sheet.delete_rows(i)
            break
            
def get_all_projects():
    sheet = get_spreadsheet().worksheet("projects")
    rows = sheet.get_all_records()
    return rows 
