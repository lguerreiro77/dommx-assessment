import os
from .sheets_adapter import SheetsAdapter


def get_repository():
    backend = os.getenv("DATA_BACKEND", "sheets")

    if backend == "sheets":
        return SheetsAdapter()

    # futuro:
    # if backend == "postgres":
    #     return PostgresAdapter()

    raise ValueError("Backend inválido")


# Alias opcional para manter compatibilidade futura
get_adapter = get_repository
