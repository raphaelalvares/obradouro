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
