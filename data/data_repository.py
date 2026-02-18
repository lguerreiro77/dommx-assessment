"""
Repositório genérico.

Não sabe se é Sheets ou Postgres.
Só delega para o adapter.
"""

from typing import List, Dict, Any
from .base_repository import BaseRepository
from .repository_factory import get_adapter


class DataRepository(BaseRepository):

    def __init__(self):
        self.adapter = get_adapter()

    def fetch_all(self, table: str) -> List[Dict[str, Any]]:
        return self.adapter.fetch_all(table)

    def insert(self, table: str, row: Dict[str, Any]) -> None:
        self.adapter.insert(table, row)

    def update(self, table: str, identifier: Any, row: Dict[str, Any]) -> None:
        self.adapter.update(table, identifier, row)

    def delete(self, table: str, identifier: Any) -> None:
        self.adapter.delete(table, identifier)
