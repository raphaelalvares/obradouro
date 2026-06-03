"""Schemas do moodboard (seções + itens de referência)."""

import datetime as dt
import uuid

from pydantic import BaseModel, Field


class SecaoCreate(BaseModel):
    id: uuid.UUID  # gerado no cliente
    nome: str = Field(min_length=1, max_length=120)
    ordem: int = 0


class SecaoUpdate(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=120)
    ordem: int | None = None


class SecaoOut(BaseModel):
    id: uuid.UUID
    nome: str
    ordem: int
    created_at: dt.datetime


class MoodboardItemOut(BaseModel):
    id: uuid.UUID
    secao_id: uuid.UUID | None = None
    legenda: str | None = None
    nome_arquivo: str
    content_type: str
    tamanho_bytes: int
    largura: int | None = None
    altura: int | None = None
    ordem: int
    seq_humano: int | None = None
    tem_thumb: bool = False
    created_at: dt.datetime
