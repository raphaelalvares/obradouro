"""Adapter de storage no Google Drive (produção — usa a conta OAuth do dono via refresh token).

Por que OAuth e NÃO service account: em Google One CONSUMER (@gmail pessoal) uma service account
tem cota própria (~15 GB) e NÃO consome os TB da conta pessoal; domain-wide delegation (o "robô" te
personificando) só existe no Workspace. Então o backend age COMO o dono, via refresh token offline
— os arquivos pertencem a ele e contam na cota dele. Escopo ``drive.file``: a app só enxerga/mexe no
que ELA cria; por isso a pasta-raiz é criada pela própria app (ver scripts/mint_drive_token.py). O
byte trafega API-only (browser → API → Drive → API); nenhum app fala com o Drive direto.

Mapeamento chave→Drive: a key opaca (ex.: ``<tenant>/<obra>/<anexo>/full.jpg``) vira uma ÁRVORE de
pastas — um folder por segmento, menos o último (= arquivo). Assim ``deletar_prefixo`` e
``listar_chaves`` ganham semântica natural (uma pasta = um prefixo) e o expurgo de um anexo é 1
delete que cascateia. Os IDs de pasta são cacheados em memória (caminho lógico → folderId).

Limitações conhecidas (aceitas p/ este backend, decisão registrada no projeto): o Drive não é CDN
(latência por arquivo — a app deve cachear), tem rate limits (~750 GB/dia de upload, cota de
req/min) e 1 conta = sem isolamento por tenant + ponto único de falha. Para escala, migrar p/ object
storage (R2/S3) atrás desta MESMA interface.
"""

import asyncio
import json
import time
import uuid

import httpx

from app.services.storage.base import StorageBackend

_TOKEN_URL = "https://oauth2.googleapis.com/token"
_API = "https://www.googleapis.com/drive/v3"
_UPLOAD = "https://www.googleapis.com/upload/drive/v3"
_FOLDER_MIME = "application/vnd.google-apps.folder"


def _segments(path: str) -> list[str]:
    """Quebra um caminho lógico em segmentos, blindando contra traversal (sem absoluto nem '..')."""
    parts = [p for p in path.strip().replace("\\", "/").split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise ValueError(f"chave de storage inválida: {path!r}")
    return parts


def _split_key(key: str) -> tuple[list[str], str]:
    """(segmentos de PASTA, nome do arquivo). Última parte é o arquivo; as demais são a árvore."""
    parts = _segments(key)
    if not parts:
        raise ValueError(f"chave de storage vazia: {key!r}")
    return parts[:-1], parts[-1]


def _q_escape(s: str) -> str:
    """Escapa aspas p/ o parâmetro q da Drive API (as keys são uuids+nome fixo, mas blindamos)."""
    return s.replace("\\", "\\\\").replace("'", "\\'")


def _bytes_do_arquivo(f: dict) -> int:
    """Bytes REAIS que um arquivo ocupa na cota do Drive. A fonte correta é ``quotaBytesUsed`` (soma
    conteúdo + revisões/metadados que pesam na cota); só cai no ``size`` quando ausente. Somar
    ``size`` é o erro clássico que SUBCONTA o Drive (arquivos sem size, revisões, etc.)."""
    q = f.get("quotaBytesUsed")
    if q is not None:
        return int(q)
    return int(f.get("size") or 0)


def _multipart_body(meta: dict, data: bytes, content_type: str, boundary: str) -> bytes:
    """Corpo multipart/related (metadata JSON + mídia) p/ criar o arquivo em 1 request."""
    b = f"--{boundary}".encode()
    end = f"--{boundary}--".encode()
    return b"\r\n".join(
        [
            b,
            b"Content-Type: application/json; charset=UTF-8",
            b"",
            json.dumps(meta).encode(),
            b,
            f"Content-Type: {content_type}".encode(),
            b"",
            data,
            end,
        ]
    )


class DriveBackend(StorageBackend):
    def __init__(
        self, client_id: str, client_secret: str, refresh_token: str, root_folder_id: str
    ) -> None:
        self._cid = client_id
        self._secret = client_secret
        self._refresh = refresh_token
        self._root = root_folder_id
        self._token: str | None = None
        self._token_exp: float = 0.0
        self._token_lock = asyncio.Lock()  # serializa o refresh do access token
        self._folders: dict[str, str] = {}  # caminho lógico → folderId (cache)
        self._folders_lock = asyncio.Lock()  # serializa create-folder (evita pastas duplicadas)
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=15.0, read=120.0, write=120.0, pool=15.0)
        )

    # ---------------------------------------------------------------- auth
    async def _access_token(self) -> str:
        if self._token and time.monotonic() < self._token_exp:
            return self._token
        async with self._token_lock:
            if self._token and time.monotonic() < self._token_exp:  # re-check sob lock
                return self._token
            r = await self._client.post(
                _TOKEN_URL,
                data={
                    "client_id": self._cid,
                    "client_secret": self._secret,
                    "refresh_token": self._refresh,
                    "grant_type": "refresh_token",
                },
            )
            r.raise_for_status()
            tok = r.json()
            self._token = tok["access_token"]
            # renova 60s antes do vencimento real (folga p/ latência)
            self._token_exp = time.monotonic() + int(tok.get("expires_in", 3600)) - 60
            return self._token

    async def _auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {await self._access_token()}"}

    # ---------------------------------------------------------------- navegação (pastas/arquivos)
    async def _find_child(
        self, parent_id: str, name: str, *, folder: bool | None
    ) -> dict | None:
        """1º filho `name` sob `parent_id` (folder: True=só pasta, False=só arquivo, None=todos)."""
        q = f"name = '{_q_escape(name)}' and '{parent_id}' in parents and trashed = false"
        if folder is True:
            q += f" and mimeType = '{_FOLDER_MIME}'"
        elif folder is False:
            q += f" and mimeType != '{_FOLDER_MIME}'"
        r = await self._client.get(
            f"{_API}/files",
            params={"q": q, "fields": "files(id,name,size,mimeType)", "pageSize": 10,
                    "spaces": "drive"},
            headers=await self._auth(),
        )
        r.raise_for_status()
        files = r.json().get("files", [])
        return files[0] if files else None

    async def _create_folder(self, parent_id: str, name: str) -> str:
        r = await self._client.post(
            f"{_API}/files",
            params={"fields": "id"},
            headers={**await self._auth(), "Content-Type": "application/json"},
            json={"name": name, "mimeType": _FOLDER_MIME, "parents": [parent_id]},
        )
        r.raise_for_status()
        return r.json()["id"]

    async def _folder_for(self, segs: list[str], *, create: bool) -> str | None:
        """Resolve a pasta no fim de `segs` (relativa à raiz). create=True cria o que faltar."""
        parent = self._root
        logical = ""
        for seg in segs:
            logical = f"{logical}/{seg}" if logical else seg
            cached = self._folders.get(logical)
            if cached:
                parent = cached
                continue
            async with self._folders_lock:
                cached = self._folders.get(logical)  # re-check sob lock (anti-duplicata)
                if cached:
                    parent = cached
                    continue
                found = await self._find_child(parent, seg, folder=True)
                if found:
                    fid = found["id"]
                elif create:
                    fid = await self._create_folder(parent, seg)
                else:
                    return None
                self._folders[logical] = fid
                parent = fid
        return parent

    async def _resolve_file(self, key: str) -> dict | None:
        folders, name = _split_key(key)
        parent = await self._folder_for(folders, create=False)
        if parent is None:
            return None
        return await self._find_child(parent, name, folder=False)

    async def _delete_id(self, file_id: str) -> None:
        r = await self._client.delete(f"{_API}/files/{file_id}", headers=await self._auth())
        if r.status_code not in (200, 204, 404):  # 404 = já não existe (idempotente)
            r.raise_for_status()

    def _forget_cache(self, prefix: str) -> None:
        """Esquece os folderIds cacheados de `prefix` (e filhos) após um delete de subárvore."""
        logical = "/".join(_segments(prefix))
        for k in [k for k in self._folders if k == logical or k.startswith(f"{logical}/")]:
            self._folders.pop(k, None)

    # ---------------------------------------------------------------- interface StorageBackend
    async def guardar(self, key: str, data: bytes, content_type: str) -> None:
        folders, name = _split_key(key)
        parent = await self._folder_for(folders, create=True)
        existing = await self._find_child(parent, name, folder=False)
        if existing:  # sobrescreve o conteúdo (mesmo id → não duplica nome no Drive)
            r = await self._client.patch(
                f"{_UPLOAD}/files/{existing['id']}",
                params={"uploadType": "media"},
                headers={**await self._auth(), "Content-Type": content_type},
                content=data,
            )
            r.raise_for_status()
            return
        boundary = uuid.uuid4().hex
        body = _multipart_body({"name": name, "parents": [parent]}, data, content_type, boundary)
        ctype = f"multipart/related; boundary={boundary}"
        r = await self._client.post(
            f"{_UPLOAD}/files",
            params={"uploadType": "multipart", "fields": "id"},
            headers={**await self._auth(), "Content-Type": ctype},
            content=body,
        )
        r.raise_for_status()

    async def recuperar(self, key: str) -> bytes:
        meta = await self._resolve_file(key)
        if meta is None:
            raise FileNotFoundError(key)
        r = await self._client.get(
            f"{_API}/files/{meta['id']}", params={"alt": "media"}, headers=await self._auth()
        )
        if r.status_code == 404:
            raise FileNotFoundError(key)
        r.raise_for_status()
        return r.content

    async def deletar(self, key: str) -> None:
        meta = await self._resolve_file(key)
        if meta is not None:
            await self._delete_id(meta["id"])

    async def existe(self, key: str) -> bool:
        return await self._resolve_file(key) is not None

    async def tamanho(self, key: str) -> int | None:
        meta = await self._resolve_file(key)
        if meta is None or meta.get("size") is None:
            return None
        return int(meta["size"])

    async def _list_children(self, parent_id: str) -> list[dict]:
        out: list[dict] = []
        page: str | None = None
        while True:
            params = {
                "q": f"'{parent_id}' in parents and trashed = false",
                "fields": "nextPageToken, files(id,name,mimeType)",
                "pageSize": 1000,
                "spaces": "drive",
            }
            if page:
                params["pageToken"] = page
            r = await self._client.get(f"{_API}/files", params=params, headers=await self._auth())
            r.raise_for_status()
            body = r.json()
            out.extend(body.get("files", []))
            page = body.get("nextPageToken")
            if not page:
                return out

    async def _walk(self, folder_id: str, path: str, out: list[str]) -> None:
        for child in await self._list_children(folder_id):
            sub = f"{path}/{child['name']}" if path else child["name"]
            if child["mimeType"] == _FOLDER_MIME:
                await self._walk(child["id"], sub, out)
            else:
                out.append(sub)

    async def listar_chaves(self, prefix: str) -> list[str]:
        segs = _segments(prefix)
        start = await self._folder_for(segs, create=False)
        if start is None:
            return []
        out: list[str] = []
        await self._walk(start, "/".join(segs), out)
        return sorted(out)

    async def deletar_prefixo(self, prefix: str) -> int:
        segs = _segments(prefix)
        if not segs:
            return 0
        folder = await self._folder_for(segs, create=False)
        if folder is None:  # não é pasta — pode ser um arquivo solto com essa key exata
            meta = await self._resolve_file(prefix)
            if meta is not None:
                await self._delete_id(meta["id"])
                return 1
            return 0
        out: list[str] = []
        await self._walk(folder, "", out)  # conta os arquivos antes do delete cascateado
        await self._delete_id(folder)
        self._forget_cache(prefix)
        return len(out)

    # ---------------------------------------------------------------- medição (painel admin)
    async def espaco_conta(self) -> dict | None:
        """storageQuota da CONTA inteira (fonte exata do 'espaço físico' — não varre pasta nenhuma).
        ``limit`` ausente = conta ilimitada (Workspace) → total None. ``usage`` é tudo (Drive/Gmail/
        Fotos); ``usageInDrive`` é só o Drive; ``usageInDriveTrash`` é a lixeira (ainda pesa)."""
        r = await self._client.get(
            f"{_API}/about", params={"fields": "storageQuota"}, headers=await self._auth()
        )
        r.raise_for_status()
        q = r.json().get("storageQuota", {})
        limit = q.get("limit")
        return {
            "total_bytes": int(limit) if limit is not None else None,
            "usado_bytes": int(q.get("usage") or 0),
            "usado_drive_bytes": int(q.get("usageInDrive") or 0),
            "lixeira_bytes": int(q.get("usageInDriveTrash") or 0),
        }

    async def _soma_prefixo(self, folder_id: str) -> int:
        """Soma recursiva dos bytes REAIS (quotaBytesUsed) sob uma pasta: desce em subpastas, ignora
        trashed, e cada pasta contribui só via seus filhos (pasta não tem tamanho). Paginado."""
        total = 0
        page: str | None = None
        while True:
            params = {
                "q": f"'{folder_id}' in parents and trashed = false",
                "fields": "nextPageToken, files(id,mimeType,quotaBytesUsed,size)",
                "pageSize": 1000,
                "spaces": "drive",
            }
            if page:
                params["pageToken"] = page
            r = await self._client.get(f"{_API}/files", params=params, headers=await self._auth())
            r.raise_for_status()
            body = r.json()
            for child in body.get("files", []):
                if child["mimeType"] == _FOLDER_MIME:
                    total += await self._soma_prefixo(child["id"])
                else:
                    total += _bytes_do_arquivo(child)
            page = body.get("nextPageToken")
            if not page:
                return total

    async def uso_prefixo_bytes(self, prefix: str) -> int | None:
        segs = _segments(prefix)
        start = await self._folder_for(segs, create=False)
        if start is None:
            return 0
        return await self._soma_prefixo(start)
