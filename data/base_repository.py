"""
base_repository.py

Contrato abstrato da camada de acesso a dados.

Objetivo:
- Definir interface padrão para operações CRUD.
- Permitir no futuro trocar Google Sheets por PostgreSQL
  sem alterar storage.py, auth.py ou renderer.

Hoje:
- Implementação concreta é DataRepository (Sheets).
- Não contém lógica executável.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any


class BaseRepository(ABC):

    @abstractmethod
    def read(self, table: str) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def append(self, table: str, row: List[Any]) -> None:
        pass

    @abstractmethod
    def update(self, table: str, row_index: int, row: List[Any]) -> None:
        pass

    @abstractmethod
    def delete(self, table: str, row_index: int) -> None:
        pass
