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


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]


@st.cache_resource
def _get_client():
    credentials = Credentials.from_service_account_file(
        os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE"),
        scopes=SCOPES
    )
    return gspread.authorize(credentials)

   
@st.cache_resource
def get_spreadsheet():
    client = _get_client()
    return client.open_by_key(os.getenv("SPREADSHEET_ID"))
    


def get_table(name: str):
    spreadsheet = get_spreadsheet()
    return spreadsheet.worksheet(name)
