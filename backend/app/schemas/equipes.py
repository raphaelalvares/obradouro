"""Schemas de Equipes (Fatia A · parte 2). Biblioteca do arquiteto (nível-tenant), reutilizável
entre obras. Cada tarefa do checklist aponta p/ uma equipe (equipe_id) — a cor pinta o Gantt.
RLS self protege o tenant; aqui só o contrato (nome, cor #RRGGBB, contato)."""

import datetime as dt
import re
import uuid

from pydantic import BaseModel, Field, field_validator

# cor de exibição (Gantt/chip): hex #RRGGBB. Mesmo CHECK do banco (0065) — poka-yoke nos dois lados.
_COR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
_COR_PADRAO = "#D8A53A"  # âmbar da marca


def _nome_limpo(v: str | None) -> str | None:
    """Trim; rejeita string só-espaços (burlaria o min_length)."""
    if v is None:
        return None
    s = v.strip()
    if not s:
        raise ValueError("nome não pode ser vazio")
    return s


def _cor_valida(v: str | None) -> str | None:
    if v is None:
        return None
    s = v.strip()
    if not _COR_RE.match(s):
        raise ValueError("cor deve ser hexadecimal no formato #RRGGBB")
    return s.upper()


class EquipeCreate(BaseModel):
    id: uuid.UUID  # gerado no cliente (dual-ID)
    nome: str = Field(min_length=1, max_length=120)
    cor: str = _COR_PADRAO
    contato: str | None = Field(default=None, max_length=200)

    @field_validator("nome")
    @classmethod
    def _v_nome(cls, v: str) -> str:
        return _nome_limpo(v)  # type: ignore[return-value]

    @field_validator("cor")
    @classmethod
    def _v_cor(cls, v: str) -> str:
        return _cor_valida(v)  # type: ignore[return-value]


class EquipeUpdate(BaseModel):
    """PATCH parcial (exclude_unset)."""

    nome: str | None = Field(default=None, min_length=1, max_length=120)
    cor: str | None = None
    contato: str | None = Field(default=None, max_length=200)
    ativo: bool | None = None

    @field_validator("nome")
    @classmethod
    def _v_nome(cls, v: str | None) -> str | None:
        return _nome_limpo(v)

    @field_validator("cor")
    @classmethod
    def _v_cor(cls, v: str | None) -> str | None:
        return _cor_valida(v)


class EquipeOut(BaseModel):
    id: uuid.UUID
    nome: str
    cor: str
    contato: str | None = None
    ativo: bool = True
    created_at: dt.datetime
    updated_at: dt.datetime
