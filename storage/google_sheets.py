import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import os


@st.cache_resource(show_spinner=False)
def get_gspread_client():

    # --------------------------
    # CLOUD (Streamlit Cloud)
    # --------------------------
    try:
        if "GOOGLE_SERVICE_ACCOUNT" in st.secrets:
            creds_dict = dict(st.secrets["GOOGLE_SERVICE_ACCOUNT"])

            creds = Credentials.from_service_account_info(
                creds_dict,
                scopes=["https://www.googleapis.com/auth/spreadsheets"]
            )

            return gspread.authorize(creds)

    except Exception:
        pass

    # --------------------------
    # LOCAL (.json file)
    # --------------------------
    if os.path.exists("service_account.json"):

        with open("service_account.json") as f:
            creds_dict = json.load(f)

        creds = Credentials.from_service_account_info(
            creds_dict,
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )

        return gspread.authorize(creds)

    raise RuntimeError("Google credentials not found.")


@st.cache_resource(show_spinner=False)
def get_spreadsheet():

    client = get_gspread_client()

    # Cloud
    try:
        spreadsheet_id = st.secrets["SPREADSHEET_ID"]
    except Exception:
        spreadsheet_id = os.getenv("SPREADSHEET_ID")

    return client.open_by_key(spreadsheet_id)


def get_sheet(name):
    spreadsheet = get_spreadsheet()
    return spreadsheet.worksheet(name)
