"""Schemas de Funções/cargos (Fatia C — efetivo do diário). Biblioteca do arquiteto (nível-tenant),
reutilizável entre obras (Pedreiro, Servente, Mestre…). RLS self protege o tenant. A quebra do
efetivo no diário aponta p/ funcao_id + guarda um snapshot do nome do cargo."""

import datetime as dt
import uuid

from pydantic import BaseModel, Field, field_validator


def _nome_limpo(v: str | None) -> str | None:
    """Trim; rejeita string só-espaços (burlaria o min_length)."""
    if v is None:
        return None
    s = v.strip()
    if not s:
        raise ValueError("nome não pode ser vazio")
    return s


class FuncaoCreate(BaseModel):
    id: uuid.UUID  # gerado no cliente (dual-ID)
    nome: str = Field(min_length=1, max_length=120)

    @field_validator("nome")
    @classmethod
    def _v_nome(cls, v: str) -> str:
        return _nome_limpo(v)  # type: ignore[return-value]


class FuncaoUpdate(BaseModel):
    """PATCH parcial (exclude_unset)."""

    nome: str | None = Field(default=None, min_length=1, max_length=120)
    ativo: bool | None = None

    @field_validator("nome")
    @classmethod
    def _v_nome(cls, v: str | None) -> str | None:
        return _nome_limpo(v)


class FuncaoOut(BaseModel):
    id: uuid.UUID
    nome: str
    ativo: bool = True
    created_at: dt.datetime
    updated_at: dt.datetime


class FuncaoSimples(BaseModel):
    """Picker do diário (funcoes_da_obra): só id + nome das funções ativas do tenant da obra."""

    id: uuid.UUID
    nome: str
