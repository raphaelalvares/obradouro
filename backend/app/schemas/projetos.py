"""Schemas do Módulo de Projeto (projeto + vínculo próprio)."""

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

# Papel no projeto: só arquiteto/cliente (prestador não participa — guard 0040).
PapelProjeto = Literal["cliente"]  # o que um convite/código concede; arquiteto = o criador


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


# ---- vínculo (espelha obra; papel no projeto = cliente) ----
class ProjetoMembroOut(BaseModel):
    id: uuid.UUID
    profile_id: uuid.UUID
    nome: str | None = None
    email: str | None = None
    papel: str
    estado: str
    created_at: dt.datetime


class ProjetoConviteCreate(BaseModel):
    email: EmailStr  # papel fixo = cliente (projeto é arquiteto↔cliente)


class ProjetoConviteEnviadoOut(BaseModel):
    profile_id: uuid.UUID
    estado: str
    action_link: str | None = None


class ProjetoCodigoOut(BaseModel):
    codigo: str
    papel: str
    expires_at: dt.datetime


class ResgatarProjetoCodigo(BaseModel):
    codigo: str


class ResgateProjetoOut(BaseModel):
    projeto_id: uuid.UUID
    estado: str  # 'pendente' (recém ou já) ou 'ativo' (já era membro) — backend dá o feedback


class ProjetoPendenteOut(BaseModel):
    projeto_id: uuid.UUID
    projeto_nome: str
    seq_humano: int | None = None
    invited_by_nome: str | None = None


class AceiteProjetoOut(BaseModel):
    projeto_id: uuid.UUID
    estado: str
