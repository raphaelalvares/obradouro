"""Schemas do micro-CRM (Comercial): oportunidades de venda."""

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, Field

# Funil enxuto (poka-yoke; espelha o CHECK da migration 0058). lead→contato→visita→proposta =
# ativos; ganho/perdido = terminais. "ganho" pode virar obra (converter).
EtapaOportunidade = Literal["lead", "contato", "visita", "proposta", "ganho", "perdido"]


class OportunidadeCreate(BaseModel):
    id: uuid.UUID  # gerado no cliente (offline/dual-ID)
    nome: str = Field(min_length=1, max_length=200)
    etapa: EtapaOportunidade = "lead"
    contato_nome: str | None = Field(default=None, max_length=200)
    contato_telefone: str | None = Field(default=None, max_length=40)
    contato_email: str | None = Field(default=None, max_length=200)
    origem: str | None = Field(default=None, max_length=120)
    valor_estimado: float | None = Field(default=None, ge=0)
    proximo_followup: dt.date | None = None
    observacoes: str | None = Field(default=None, max_length=2000)


class OportunidadeUpdate(BaseModel):
    """PATCH parcial (exclude_unset): só os campos enviados mudam; enviar null limpa o campo."""

    nome: str | None = Field(default=None, min_length=1, max_length=200)
    etapa: EtapaOportunidade | None = None
    contato_nome: str | None = Field(default=None, max_length=200)
    contato_telefone: str | None = Field(default=None, max_length=40)
    contato_email: str | None = Field(default=None, max_length=200)
    origem: str | None = Field(default=None, max_length=120)
    valor_estimado: float | None = Field(default=None, ge=0)
    proximo_followup: dt.date | None = None
    observacoes: str | None = Field(default=None, max_length=2000)


class OportunidadeConverter(BaseModel):
    obra_id: uuid.UUID  # id da NOVA obra, gerado no cliente (dual-ID)


class OportunidadeCriarProjeto(BaseModel):
    projeto_id: uuid.UUID  # id do NOVO projeto, gerado no cliente (dual-ID)
    nome: str | None = Field(default=None, min_length=1, max_length=200)  # default = nome do lead


class OportunidadeVincularProjeto(BaseModel):
    projeto_id: uuid.UUID | None = None  # null = desvincular


class OportunidadeOut(BaseModel):
    id: uuid.UUID
    nome: str
    etapa: EtapaOportunidade
    obra_id: uuid.UUID | None = None
    projeto_id: uuid.UUID | None = None
    contato_nome: str | None = None
    contato_telefone: str | None = None
    contato_email: str | None = None
    origem: str | None = None
    valor_estimado: float | None = None
    proximo_followup: dt.date | None = None
    observacoes: str | None = None
    comentarios_count: int = 0
    seq_humano: int | None = None
    created_at: dt.datetime
    updated_at: dt.datetime


class ComentarioCreate(BaseModel):
    id: uuid.UUID  # gerado no cliente (offline/dual-ID)
    texto: str = Field(min_length=1, max_length=2000)


class ComentarioUpdate(BaseModel):
    texto: str = Field(min_length=1, max_length=2000)


class ComentarioOut(BaseModel):
    id: uuid.UUID
    texto: str
    autor_nome: str | None = None
    created_at: dt.datetime
    updated_at: dt.datetime
