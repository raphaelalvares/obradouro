"""Schemas de obras."""

import datetime as dt
import uuid

from pydantic import BaseModel, Field


class ObraCreate(BaseModel):
    id: uuid.UUID  # gerado no cliente (suporte a offline)
    nome: str = Field(min_length=1, max_length=200)


class ObraRename(BaseModel):
    nome: str = Field(min_length=1, max_length=200)


class ObraOut(BaseModel):
    id: uuid.UUID
    nome: str
    status: str
    seq_humano: int | None = None
    created_at: dt.datetime
    # papel do usuário corrente na obra (arquiteto|cliente|prestador) — o front gateia a UI com ele.
    # Ausente na resposta de criação (o criador é sempre arquiteto); presente em get/list.
    meu_papel: str | None = None
