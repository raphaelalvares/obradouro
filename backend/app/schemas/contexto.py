"""Schemas do cartão de CONTEXTO do cliente (1:1 com a oportunidade).

PERFIL = estruturado (o que regras/automação leem). RESUMO = texto curto (o "claude.md" do cliente),
com teto rígido — pro 3B ler barato e pro arquiteto manter conciso.
"""

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, Field

CanalPreferido = Literal["whatsapp", "telefone", "email"]


class ContextoPerfil(BaseModel):
    canal_preferido: CanalPreferido | None = None
    melhor_horario: str | None = Field(default=None, max_length=80)
    cadencia_dias: int | None = Field(default=None, ge=1, le=365)  # follow-up desejado
    decisor: str | None = Field(default=None, max_length=120)
    sensivel_a_preco: bool | None = None


class ContextoUpsert(BaseModel):
    perfil: ContextoPerfil = Field(default_factory=ContextoPerfil)
    resumo: str | None = Field(default=None, max_length=600)  # cap do "cartão de contexto"


class ContextoOut(BaseModel):
    oportunidade_id: uuid.UUID
    perfil: ContextoPerfil = Field(default_factory=ContextoPerfil)
    resumo: str | None = None
    existe: bool = False  # false = ainda sem contexto salvo (ou migration 0087 não aplicada)
    atualizado_em: dt.datetime | None = None
