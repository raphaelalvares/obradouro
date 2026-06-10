"""Schemas do Catálogo de serviços (Livro de referências · Fatia 1).

Biblioteca do arquiteto (nível-tenant). Custos são UNITÁRIOS (R$/unidade) — diferente de
orcamento_itens, que guarda subtotal por linha. A conversão subtotal↔unitário mora no service
(fonte única da matemática). Teto dos campos de custo = bem abaixo do numeric(14,4) p/ overflow
virar 422 (não 500).
"""

import datetime as dt
import uuid

from pydantic import BaseModel, Field, field_validator

# teto generoso p/ custo unitário (R$/unidade) — cabe no numeric(14,4) com folga; barra overflow.
_CUSTO_MAX = 99_999_999.9999


def _desc_limpa(v: str | None) -> str | None:
    """Trim; rejeita string só-espaços (burlaria o min_length)."""
    if v is None:
        return None
    s = v.strip()
    if not s:
        raise ValueError("descrição não pode ser vazia")
    return s


class ServicoCreate(BaseModel):
    id: uuid.UUID  # gerado no cliente (dual-ID)
    descricao: str = Field(min_length=1, max_length=300)
    unidade: str | None = Field(default=None, max_length=20)
    custo_mo: float = Field(default=0, ge=0, le=_CUSTO_MAX)
    custo_material: float = Field(default=0, ge=0, le=_CUSTO_MAX)
    custo_equipamento: float = Field(default=0, ge=0, le=_CUSTO_MAX)
    etapa_sugerida: str | None = Field(default=None, max_length=200)

    @field_validator("descricao")
    @classmethod
    def _v_desc(cls, v: str) -> str:
        return _desc_limpa(v)  # type: ignore[return-value]


class ServicoUpdate(BaseModel):
    """PATCH parcial (exclude_unset)."""

    descricao: str | None = Field(default=None, min_length=1, max_length=300)
    unidade: str | None = Field(default=None, max_length=20)
    custo_mo: float | None = Field(default=None, ge=0, le=_CUSTO_MAX)
    custo_material: float | None = Field(default=None, ge=0, le=_CUSTO_MAX)
    custo_equipamento: float | None = Field(default=None, ge=0, le=_CUSTO_MAX)
    etapa_sugerida: str | None = Field(default=None, max_length=200)
    ativo: bool | None = None

    @field_validator("descricao")
    @classmethod
    def _v_desc(cls, v: str | None) -> str | None:
        return _desc_limpa(v)


class PromoverServicoIn(BaseModel):
    """'Salvar no catálogo' a partir de uma linha de orçamento (subtotais + qtd).

    O service calcula o custo UNITÁRIO = subtotal / qtd (qtd ausente/0 → 1). Faz merge por
    descricao_norm (atualiza a referência se já existir).
    """

    descricao: str = Field(min_length=1, max_length=300)
    unidade: str | None = Field(default=None, max_length=20)
    quantidade: float | None = Field(default=None, ge=0)
    # mesmos tetos de ServicoCreate: barra o subtotal absurdo já na entrada (o unitário ainda é
    # revalidado no service, pois dividir por qtd < 1 pode estourar o teto mesmo com valor dentro).
    valor_mo: float = Field(default=0, ge=0, le=_CUSTO_MAX)
    valor_material: float = Field(default=0, ge=0, le=_CUSTO_MAX)
    valor_equipamento: float = Field(default=0, ge=0, le=_CUSTO_MAX)
    etapa_sugerida: str | None = Field(default=None, max_length=200)

    @field_validator("descricao")
    @classmethod
    def _v_desc(cls, v: str) -> str:
        return _desc_limpa(v)  # type: ignore[return-value]


class ServicoOut(BaseModel):
    id: uuid.UUID
    descricao: str
    unidade: str | None = None
    custo_mo: float = 0
    custo_material: float = 0
    custo_equipamento: float = 0
    etapa_sugerida: str | None = None
    ativo: bool = True
    created_at: dt.datetime
    updated_at: dt.datetime


class ServicoPromovidoOut(ServicoOut):
    """Saída do 'salvar no catálogo' — diz se foi criado (true) ou atualizado (false)."""

    criado: bool = True
