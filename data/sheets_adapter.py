"""
SheetsAdapter

Implementação concreta do backend Google Sheets.

Responsável por:
- fetch_all
- insert
- update (retorna bool)
- delete (retorna bool)
- upsert
- begin / commit / rollback (no-op)

Toda conexão vem exclusivamente de sheets_client.
Nenhuma credencial ou lógica de conexão aqui.
"""

import streamlit as st
from typing import List, Dict, Any
from data.sheets_client import get_table


@st.cache_data(ttl=120, show_spinner=False)
def _fetch_cached_table(table: str) -> List[Dict[str, Any]]:
    ws = get_table(table)
    return ws.get_all_records()


class SheetsAdapter:

    # =========================
    # READ
    # =========================
    def fetch_all(self, table: str) -> List[Dict[str, Any]]:
        return _fetch_cached_table(table)

    # =========================
    # INSERT (puro)
    # =========================
    def insert(self, table: str, row: Dict[str, Any]) -> None:
        ws = get_table(table)
        headers = ws.row_values(1)
        ordered = [row.get(col, "") for col in headers]
        ws.append_row(ordered)
        _fetch_cached_table.clear(table)

    # =========================
    # UPDATE
    # =========================
    def update(self, table: str, filters: Dict[str, Any], values: Dict[str, Any]) -> bool:

        ws = get_table(table)
        rows = ws.get_all_records()
        headers = ws.row_values(1)

        updated = False

        for idx, row in enumerate(rows, start=2):
            if all(str(row.get(k)) == str(v) for k, v in filters.items()):

                for col, val in values.items():
                    if col in headers:
                        col_index = headers.index(col) + 1
                        ws.update_cell(idx, col_index, val)

                updated = True

        if updated:
            _fetch_cached_table.clear(table)

        return updated

    # =========================
    # DELETE (multi-row safe)
    # =========================
    def delete(self, table: str, filters: Dict[str, Any]) -> bool:

        ws = get_table(table)
        rows = ws.get_all_records()

        matched_indexes = []

        for idx, row in enumerate(rows, start=2):
            if all(str(row.get(k)) == str(v) for k, v in filters.items()):
                matched_indexes.append(idx)

        if not matched_indexes:
            return False

        for idx in sorted(matched_indexes, reverse=True):
            ws.delete_rows(idx)

        _fetch_cached_table.clear(table)
        return True

    # =========================
    # UPSERT UNIQUE KEY SAFE
    # =========================
    def upsert_unique(self, table: str, unique_key: str, row: Dict[str, Any]) -> None:
        """
        Garante unicidade por chave.
        Se existir, atualiza.
        Se múltiplos existirem, consolida.
        Se não existir, insere.
        """

        ws = get_table(table)
        headers = ws.row_values(1)
        rows = ws.get_all_records()

        key_value = str(row.get(unique_key)).strip()
        matched_indexes = []

        for idx, r in enumerate(rows, start=2):
            if str(r.get(unique_key, "")).strip() == key_value:
                matched_indexes.append(idx)

        if matched_indexes:

            # Atualiza a primeira
            first_idx = matched_indexes[0]

            for col, val in row.items():
                if col in headers:
                    col_index = headers.index(col) + 1
                    ws.update_cell(first_idx, col_index, val)

            # Remove duplicatas se existirem
            if len(matched_indexes) > 1:
                for dup in sorted(matched_indexes[1:], reverse=True):
                    ws.delete_rows(dup)

        else:
            ordered = [row.get(col, "") for col in headers]
            ws.append_row(ordered)

        _fetch_cached_table.clear(table)

    # =========================
    # UPSERT genérico
    # =========================
    def upsert(self, table: str, filters: Dict[str, Any], values: Dict[str, Any]) -> None:

        updated = self.update(table, filters, values)

        if not updated:
            row = {**filters, **values}
            self.insert(table, row)

    # =========================
    # TRANSACTION (NO-OP)
    # =========================
    def begin(self):
        pass

    def commit(self):
        pass

    def rollback(self):
        pass
