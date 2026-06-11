"""Schemas do Acompanhamento (Fatia C): diário de obra, pendências (punch list) e avanço/curva S.

Diário e pendência são entidades por-obra (dual-ID + seq); quem EXECUTA a obra escreve, cliente lê.
A curva S é DERIVADA do checklist (sem tabela) — avanço ponderado por custo (fallback contagem).
"""

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Prioridade = Literal["baixa", "media", "alta"]
StatusPendencia = Literal["aberta", "resolvida"]


def _texto_limpo(v: str | None) -> str | None:
    if v is None:
        return None
    s = v.strip()
    if not s:
        raise ValueError("texto não pode ser vazio")
    return s


# ============================ efetivo do diário (quebra por função) ============================
class EfetivoItem(BaseModel):
    """Uma linha do efetivo no PAYLOAD (função × quantidade). O `nome` não vem na entrada — o
    backend grava o snapshot canônico vindo da biblioteca; aqui basta funcao_id + qtd."""

    funcao_id: uuid.UUID
    qtd: int = Field(ge=1, le=100000)


class EfetivoItemOut(BaseModel):
    funcao_id: uuid.UUID
    nome: str  # snapshot gravado no diário (sobrevive a renomear/arquivar a função)
    qtd: int


# ============================ diário de obra ============================
class DiarioCreate(BaseModel):
    id: uuid.UUID  # gerado no cliente (dual-ID)
    data: dt.date
    texto: str = Field(min_length=1, max_length=4000)
    clima: str | None = Field(default=None, max_length=60)
    efetivo_itens: list[EfetivoItem] = Field(default_factory=list, max_length=100)

    @field_validator("texto")
    @classmethod
    def _v_texto(cls, v: str) -> str:
        return _texto_limpo(v)  # type: ignore[return-value]


class DiarioUpdate(BaseModel):
    """PATCH parcial (exclude_unset). efetivo_itens presente (mesmo []) troca a quebra do dia."""

    data: dt.date | None = None
    texto: str | None = Field(default=None, min_length=1, max_length=4000)
    clima: str | None = Field(default=None, max_length=60)
    efetivo_itens: list[EfetivoItem] | None = Field(default=None, max_length=100)

    @field_validator("texto")
    @classmethod
    def _v_texto(cls, v: str | None) -> str | None:
        return _texto_limpo(v)


class DiarioOut(BaseModel):
    id: uuid.UUID
    data: dt.date
    texto: str
    clima: str | None = None
    efetivo: int | None = None  # TOTAL (soma das qtds), mantido pelo backend
    efetivo_itens: list[EfetivoItemOut] = []
    seq_humano: int | None = None
    created_by: uuid.UUID | None = None  # p/ o front gatear edição (prestador só a própria)
    autor_nome: str | None = None
    n_fotos: int = 0
    created_at: dt.datetime
    updated_at: dt.datetime


# ============================ pendências (punch list) ============================
class PendenciaCreate(BaseModel):
    id: uuid.UUID
    descricao: str = Field(min_length=1, max_length=1000)
    ambiente_id: uuid.UUID | None = None
    equipe_id: uuid.UUID | None = None
    prioridade: Prioridade = "media"

    @field_validator("descricao")
    @classmethod
    def _v_desc(cls, v: str) -> str:
        return _texto_limpo(v)  # type: ignore[return-value]


class PendenciaUpdate(BaseModel):
    """PATCH parcial. Mudar `status` carimba resolvido_por/resolvido_em no service."""

    descricao: str | None = Field(default=None, min_length=1, max_length=1000)
    ambiente_id: uuid.UUID | None = None
    equipe_id: uuid.UUID | None = None
    prioridade: Prioridade | None = None
    status: StatusPendencia | None = None

    @field_validator("descricao")
    @classmethod
    def _v_desc(cls, v: str | None) -> str | None:
        return _texto_limpo(v)


class PendenciaOut(BaseModel):
    id: uuid.UUID
    descricao: str
    ambiente_id: uuid.UUID | None = None
    equipe_id: uuid.UUID | None = None
    prioridade: Prioridade = "media"
    status: StatusPendencia = "aberta"
    resolvido_por: uuid.UUID | None = None
    resolvido_por_nome: str | None = None
    resolvido_em: dt.datetime | None = None
    seq_humano: int | None = None
    created_by: uuid.UUID | None = None  # p/ o front gatear exclusão (prestador só a própria)
    autor_nome: str | None = None
    n_fotos: int = 0
    created_at: dt.datetime
    updated_at: dt.datetime


# ============================ avanço físico / curva S ============================
class CurvaPonto(BaseModel):
    data: dt.date
    planejado_pct: float  # 0..100 acumulado
    real_pct: float       # 0..100 acumulado


class AvancoOut(BaseModel):
    por_custo: bool            # True = avanço ponderado por custo; False = por contagem de tarefas
    peso_total: float          # soma dos pesos (custo total ou nº de folhas)
    real_pct: float            # avanço físico realizado até hoje (0..100)
    planejado_pct: float       # planejado até hoje (0..100)
    inicio: dt.date | None = None
    fim: dt.date | None = None
    pontos: list[CurvaPonto] = []
