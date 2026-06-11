"""Schemas de anexos (mídia informal de etapa/item)."""

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel

# Poka-yoke no contrato: alvo = etapa, item, diário ou pendência (= check do banco).
ParentType = Literal["etapa", "checklist_item", "diario", "pendencia"]


class AnexoCreate(BaseModel):
    # id gerado no cliente (offline/dual-ID); tenant_id/criado_por nunca vêm do cliente.
    id: uuid.UUID
    parent_type: ParentType
    parent_id: uuid.UUID


class AnexoOut(BaseModel):
    id: uuid.UUID
    parent_type: str
    parent_id: uuid.UUID
    nome_arquivo: str
    content_type: str
    tamanho_bytes: int
    largura: int | None = None
    altura: int | None = None
    criado_por: uuid.UUID | None = None
    criado_por_nome: str | None = None
    seq_humano: int | None = None
    tem_thumb: bool = False
    created_at: dt.datetime
