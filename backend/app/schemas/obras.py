"""Schemas de obras."""

import datetime as dt
import uuid

from pydantic import BaseModel, Field


class ObraCreate(BaseModel):
    id: uuid.UUID  # gerado no cliente (suporte a offline)
    nome: str = Field(min_length=1, max_length=200)


class ObraRename(BaseModel):
    nome: str = Field(min_length=1, max_length=200)


class ObraDatas(BaseModel):
    """Início/fim da obra (base do cronograma macro). Ambas nulas = limpa."""

    data_inicio: dt.date | None = None
    data_fim: dt.date | None = None


class ObraOut(BaseModel):
    id: uuid.UUID
    nome: str
    status: str
    seq_humano: int | None = None
    created_at: dt.datetime
    # janela da obra (cronograma macro)
    data_inicio: dt.date | None = None
    data_fim: dt.date | None = None
    # papel do usuário corrente na obra (arquiteto|cliente|prestador) — o front gateia a UI com ele.
    # Ausente na resposta de criação (o criador é sempre arquiteto); presente em get/list.
    meu_papel: str | None = None
