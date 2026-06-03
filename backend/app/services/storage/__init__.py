"""Seleção do backend de storage (factory). O resto da app importa só `get_storage()` e a
interface `StorageBackend` — nunca um adapter concreto."""

from functools import lru_cache

from app.core.config import get_settings
from app.services.storage.base import StorageBackend
from app.services.storage.local import LocalDiskBackend

__all__ = ["StorageBackend", "get_storage"]


@lru_cache
def get_storage() -> StorageBackend:
    """Instância única do backend de bytes, escolhida por STORAGE_BACKEND. Drive/Supabase entram
    aqui como novos `case`, atrás da MESMA interface (sem tocar no service de anexos)."""
    settings = get_settings()
    backend = settings.STORAGE_BACKEND.lower()
    if backend == "local":
        return LocalDiskBackend(settings.STORAGE_DIR)
    raise NotImplementedError(
        f"STORAGE_BACKEND={settings.STORAGE_BACKEND!r} não implementado. "
        "Opções atuais: 'local'. Drive/Supabase: adicionar um StorageBackend e registrar aqui."
    )
