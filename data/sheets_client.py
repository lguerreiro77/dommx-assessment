"""
sheets_client.py

Responsável exclusivamente por:

- Criar cliente Google Sheets
- Abrir Spreadsheet
- Fornecer worksheet por nome

Infraestrutura pura.
Nenhuma regra de negócio aqui.
"""

import os
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]


@st.cache_resource
def _get_client():

    credentials = None

    # tentativa Streamlit secrets (cloud)
    try:
        if "gcp_service_account" in st.secrets:
            credentials = Credentials.from_service_account_info(
                st.secrets["gcp_service_account"],
                scopes=SCOPES
            )
    except Exception:
        pass

    # fallback local .env / arquivo
    if credentials is None:

        service_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")

        if not service_file:
            raise RuntimeError(
                "Google credentials not configured. Use secrets.toml or GOOGLE_SERVICE_ACCOUNT_FILE."
            )

        credentials = Credentials.from_service_account_file(
            service_file,
            scopes=SCOPES
        )

    return gspread.authorize(credentials)


@st.cache_resource
def get_spreadsheet():

    spreadsheet_id = os.getenv("SPREADSHEET_ID") or st.secrets.get("SPREADSHEET_ID")

    if not spreadsheet_id:
        raise RuntimeError("SPREADSHEET_ID not configured")

    client = _get_client()

    return client.open_by_key(spreadsheet_id)


def get_table(name: str):
    spreadsheet = get_spreadsheet()
    return spreadsheet.worksheet(name)