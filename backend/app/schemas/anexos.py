"""Schemas de anexos (mídia informal de etapa/item)."""

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Poka-yoke no contrato: alvo = etapa, item, diário, pendência ou tarefa-do-diário (check do banco).
ParentType = Literal["etapa", "checklist_item", "diario", "pendencia", "diario_tarefa"]


def _legenda_limpa(v: str | None) -> str | None:
    if v is None:
        return None
    s = v.strip()
    return s or None  # "" / só espaços → None (sem legenda)


class AnexoCreate(BaseModel):
    # id gerado no cliente (offline/dual-ID); tenant_id/criado_por nunca vêm do cliente.
    id: uuid.UUID
    parent_type: ParentType
    parent_id: uuid.UUID
    legenda: str | None = Field(default=None, max_length=300)

    @field_validator("legenda")
    @classmethod
    def _v_legenda(cls, v: str | None) -> str | None:
        return _legenda_limpa(v)


class LegendaUpdate(BaseModel):
    legenda: str | None = Field(default=None, max_length=300)

    @field_validator("legenda")
    @classmethod
    def _v_legenda(cls, v: str | None) -> str | None:
        return _legenda_limpa(v)


class AnexoOut(BaseModel):
    id: uuid.UUID
    parent_type: str
    parent_id: uuid.UUID
    nome_arquivo: str
    content_type: str
    tamanho_bytes: int
    largura: int | None = None
    altura: int | None = None
    legenda: str | None = None
    criado_por: uuid.UUID | None = None
    criado_por_nome: str | None = None
    seq_humano: int | None = None
    tem_thumb: bool = False
    created_at: dt.datetime
