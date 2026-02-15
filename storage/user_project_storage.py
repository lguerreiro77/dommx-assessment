import streamlit as st
from datetime import datetime
from storage.google_sheets import get_sheet
from storage.google_sheets import get_spreadsheet


# -------------------------
# GET ALL PROJECTS
# -------------------------
@st.cache_data(ttl=60, show_spinner=False)
def get_all_projects():
    sheet = get_sheet("projects")
    return sheet.get_all_records()


# -------------------------
# GET PROJECTS FOR USER
# -------------------------
@st.cache_data(ttl=30, show_spinner=False)
def get_projects_for_user(user_id):
    sheet = get_sheet("usersprojects")
    rows = sheet.get_all_records()

    return [
        r["project_id"]
        for r in rows
        if r["user_id"] == user_id
    ]


# -------------------------
# ASSOCIATE USERS PROJECTS
# -------------------------

def associate_users_projects(user_ids, project_ids, created_by):

    sheet = get_sheet("usersprojects")
    existing = sheet.get_all_records()

    existing_pairs = {
        (row["user_id"], row["project_id"])
        for row in existing
    }

    timestamp = datetime.utcnow().isoformat()
    rows_to_add = []

    for u in user_ids:
        for p in project_ids:
            if (u, p) not in existing_pairs:
                rows_to_add.append([u, p, timestamp, created_by])

    if rows_to_add:
        sheet.append_rows(rows_to_add)




def get_all_user_projects():
    sheet = get_sheet("usersprojects")
    return sheet.get_all_records()


# -------------------------------------------------
# GET ALL ASSOCIATIONS
# -------------------------------------------------
def get_all_user_projects():
    sheet = get_sheet("usersprojects")
    return sheet.get_all_records()


# -------------------------------------------------
# GET PROJECTS FOR A USER
# -------------------------------------------------
def get_user_projects(email_hash: str):
    sheet = get_sheet("usersprojects")
    rows = sheet.get_all_records()

    return [
        r["project_id"]
        for r in rows
        if r.get("email_hash") == email_hash
    ]


# -------------------------------------------------
# SAVE MULTIPLE ASSOCIATIONS (OVERWRITE USER)
# -------------------------------------------------
def save_user_projects(email_hash: str, project_ids: list):

    sheet = get_sheet("usersprojects")
    rows = sheet.get_all_records()

    # Remove existing associations for that user
    new_rows = [
        r for r in rows
        if r.get("email_hash") != email_hash
    ]

    # Clear sheet (keep header)
    sheet.clear()
    sheet.append_row(["email_hash", "project_id"])

    # Rewrite filtered rows
    for r in new_rows:
        sheet.append_row([r["email_hash"], r["project_id"]])

    # Insert new associations
    for pid in project_ids:
        sheet.append_row([email_hash, pid])
        
def associate_users_projects(user_ids: list, project_ids: list, created_by: str):

    sheet = get_sheet("usersprojects")
    rows = sheet.get_all_records()

    existing = {(r["user_id"], r["project_id"]) for r in rows}

    now = datetime.utcnow().isoformat()

    for user_id in user_ids:
        for project_id in project_ids:

            if (user_id, project_id) not in existing:

                sheet.append_row([
                    user_id,
                    project_id,
                    now,
                    created_by
                ])       