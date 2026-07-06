"""Schemas do Módulo de Projeto (projeto + membros materializados)."""

import datetime as dt
import uuid

from pydantic import BaseModel, Field


class ProjetoCreate(BaseModel):
    id: uuid.UUID  # gerado no cliente (offline/dual-ID)
    nome: str = Field(min_length=1, max_length=200)
    briefing: dict = Field(default_factory=dict)  # onboarding (estruturado no front)
    # alterações incluídas no contrato — o ARQUITETO define (None = não controla; nunca sinaliza)
    revisoes_incluidas: int | None = Field(default=None, ge=0)


class ProjetoUpdate(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=200)
    briefing: dict | None = None
    revisoes_incluidas: int | None = Field(default=None, ge=0)


class VincularObra(BaseModel):
    # obra_id None = desvincular; uuid = vincular (a obra tem de ser do mesmo tenant — guard 0040)
    obra_id: uuid.UUID | None = None


class ProjetoOut(BaseModel):
    id: uuid.UUID
    nome: str
    obra_id: uuid.UUID | None = None
    briefing: dict = Field(default_factory=dict)
    revisoes_incluidas: int | None = None
    seq_humano: int | None = None
    created_at: dt.datetime
    # papel do USUÁRIO CORRENTE neste projeto (arquiteto|cliente) — o front usa p/ gatear a UI.
    # None só se a sessão não for membro ativo (não deveria acontecer pós-RLS).
    meu_papel: str | None = None


