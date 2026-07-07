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
    if backend == "drive":
        # import tardio: só quem usa Drive carrega o adapter (mantém 'local'/testes independentes).
        from app.services.storage.drive import DriveBackend

        faltando = [
            nome
            for nome, valor in {
                "GOOGLE_DRIVE_CLIENT_ID": settings.GOOGLE_DRIVE_CLIENT_ID,
                "GOOGLE_DRIVE_CLIENT_SECRET": settings.GOOGLE_DRIVE_CLIENT_SECRET,
                "GOOGLE_DRIVE_REFRESH_TOKEN": settings.GOOGLE_DRIVE_REFRESH_TOKEN,
                "GOOGLE_DRIVE_ROOT_FOLDER_ID": settings.GOOGLE_DRIVE_ROOT_FOLDER_ID,
            }.items()
            if not valor
        ]
        if faltando:
            raise RuntimeError(
                "STORAGE_BACKEND=drive requer as variáveis: " + ", ".join(faltando)
            )
        return DriveBackend(
            client_id=settings.GOOGLE_DRIVE_CLIENT_ID,
            client_secret=settings.GOOGLE_DRIVE_CLIENT_SECRET.get_secret_value(),
            refresh_token=settings.GOOGLE_DRIVE_REFRESH_TOKEN.get_secret_value(),
            root_folder_id=settings.GOOGLE_DRIVE_ROOT_FOLDER_ID,
        )
    raise NotImplementedError(
        f"STORAGE_BACKEND={settings.STORAGE_BACKEND!r} não implementado. "
        "Opções atuais: 'local', 'drive'. Supabase/S3: novo StorageBackend registrado aqui."
    )
