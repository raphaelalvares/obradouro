"""Adapter de storage em DISCO LOCAL (Fase 4 — backend de dev, sem credencial externa).

Exercita o pipeline API-only completo (browser → API → disco → API → browser) e prova que a
interface é trocável: Drive/S3/Supabase entram no lugar sem tocar no service de anexos. NÃO é o
backend de produção (os bytes ficam na máquina/volume do backend; não sobrevivem a um redeploy sem
volume persistente). Para produção, implementar outro StorageBackend e mudar STORAGE_BACKEND.

IO de disco é bloqueante → roda em thread (anyio.to_thread) p/ não travar o event loop.
"""

import shutil
from pathlib import Path

import anyio

from app.services.storage.base import StorageBackend


def _safe_segments(key: str) -> str:
    """Chaves são geradas por nós (uuids + nome fixo), mas blindamos contra traversal mesmo assim:
    sem componentes absolutos nem '..'."""
    key = key.strip().lstrip("/\\")
    parts = [p for p in key.replace("\\", "/").split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise ValueError(f"chave de storage inválida: {key!r}")
    return "/".join(parts)


class LocalDiskBackend(StorageBackend):
    def __init__(self, root: str) -> None:
        self._root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        p = (self._root / _safe_segments(key)).resolve()
        # defesa em profundidade: o caminho final tem de continuar dentro da raiz
        if not p.is_relative_to(self._root):
            raise ValueError(f"chave de storage fora da raiz: {key!r}")
        return p

    def _guardar_sync(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)  # rename atômico → nunca expõe arquivo meio-escrito

    async def guardar(self, key: str, data: bytes, content_type: str) -> None:  # noqa: ARG002
        await anyio.to_thread.run_sync(self._guardar_sync, key, data)

    async def recuperar(self, key: str) -> bytes:
        return await anyio.to_thread.run_sync(lambda: self._path(key).read_bytes())

    def _deletar_sync(self, key: str) -> None:
        path = self._path(key)
        path.unlink(missing_ok=True)
        # limpa diretórios vazios subindo até a raiz (não deixa lixo de árvore)
        parent = path.parent
        while parent != self._root and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent

    async def deletar(self, key: str) -> None:
        await anyio.to_thread.run_sync(self._deletar_sync, key)

    async def existe(self, key: str) -> bool:
        return await anyio.to_thread.run_sync(lambda: self._path(key).is_file())

    async def tamanho(self, key: str) -> int | None:
        def _stat() -> int | None:
            p = self._path(key)
            return p.stat().st_size if p.is_file() else None

        return await anyio.to_thread.run_sync(_stat)

    def _listar_sync(self, prefix: str) -> list[str]:
        base = self._path(prefix) if prefix else self._root
        if not base.exists():
            return []
        roots = [base] if base.is_dir() else [base.parent]
        out: list[str] = []
        for r in roots:
            for f in r.rglob("*"):
                if f.is_file() and not f.name.endswith(".tmp"):
                    out.append(f.relative_to(self._root).as_posix())
        return sorted(out)

    async def listar_chaves(self, prefix: str) -> list[str]:
        return await anyio.to_thread.run_sync(self._listar_sync, prefix)

    def _deletar_prefixo_sync(self, prefix: str) -> int:
        base = self._path(prefix)
        if not base.exists():
            return 0
        if base.is_file():
            base.unlink(missing_ok=True)
            return 1
        n = sum(1 for f in base.rglob("*") if f.is_file())
        shutil.rmtree(base, ignore_errors=True)
        return n

    async def deletar_prefixo(self, prefix: str) -> int:
        return await anyio.to_thread.run_sync(self._deletar_prefixo_sync, prefix)
