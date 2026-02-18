"""
data_client.py

Cliente genérico de conexão com backend de dados.

HOJE:
- Implementação ativa: Google Sheets

AMANHÃ:
- Pode implementar PostgreSQL
- Pode implementar SQL Server
- Pode implementar qualquer banco relacional

A interface pública deste módulo NÃO MUDA.
Apenas a implementação interna da conexão muda.

Fluxo arquitetural:
storage.py → repository → data_client → backend real
"""

import os
import streamlit as st
from typing import Any

# ============================================
# CONFIGURAÇÃO DE BACKEND
# ============================================

BACKEND_TYPE = os.getenv("DATA_BACKEND", "sheets")
# sheets | postgres | sqlserver


# ============================================
# CONEXÃO GENÉRICA
# ============================================

@st.cache_resource
def get_connection() -> Any:
    """
    Retorna conexão com backend ativo.
    Cacheada para evitar múltiplas conexões.
    """

    if BACKEND_TYPE == "sheets":
        return _get_sheets_connection()

    elif BACKEND_TYPE == "postgres":
        return _get_postgres_connection()

    elif BACKEND_TYPE == "sqlserver":
        return _get_sqlserver_connection()

    else:
        raise ValueError("DATA_BACKEND inválido")


# ============================================
# SHEETS IMPLEMENTATION (ATUAL)
# ============================================

def _get_sheets_connection():
    import gspread
    from google.oauth2.service_account import Credentials

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    credentials = Credentials.from_service_account_file(
        os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE"),
        scopes=scopes
    )

    client = gspread.authorize(credentials)
    spreadsheet = client.open(os.getenv("SPREADSHEET_NAME"))

    return spreadsheet


def get_table(table_name: str):
    """
    Retorna handler da tabela independente do backend.
    """

    conn = get_connection()

    if BACKEND_TYPE == "sheets":
        return conn.worksheet(table_name)

    elif BACKEND_TYPE in ("postgres", "sqlserver"):
        return conn  # banco retorna conexão direta


# ============================================
# FUTURAS IMPLEMENTAÇÕES (PLACEHOLDER)
# ============================================

def _get_postgres_connection():
    """
    Implementação futura PostgreSQL.
    """
    import psycopg2

    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        port=os.getenv("DB_PORT")
    )


def _get_sqlserver_connection():
    """
    Implementação futura SQL Server.
    """
    import pyodbc

    return pyodbc.connect(
        os.getenv("SQLSERVER_CONNECTION_STRING")
    )
