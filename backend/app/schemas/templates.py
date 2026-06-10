"""Schemas dos Templates de ambiente (Livro de referências · Fatia 2).

Template = receita por tipo×nível ("Banheiro · alto padrão") que lista serviços do catálogo (0063)
com regra de quantidade: fixa (por_area=false → qtd=fator) ou por m² (por_area=true → fator×área).
Aplicar a um cômodo gera linhas no orçamento (subtotal = custo_unit × qtd, calculado no backend).
"""

import datetime as dt
import uuid

from pydantic import BaseModel, Field, field_validator

_FATOR_MAX = 9_999_999.9999
_AREA_MAX = 99_999_999.99


def _texto_limpo(v: str | None) -> str | None:
    if v is None:
        return None
    s = v.strip()
    if not s:
        raise ValueError("não pode ser vazio")
    return s


# ---------------- template (cabeçalho) ----------------
class TemplateCreate(BaseModel):
    id: uuid.UUID
    tipo: str = Field(min_length=1, max_length=120)
    nivel: str = Field(min_length=1, max_length=120)
    area_referencia: float | None = Field(default=None, ge=0, le=_AREA_MAX)

    @field_validator("tipo", "nivel")
    @classmethod
    def _v(cls, v: str) -> str:
        return _texto_limpo(v)  # type: ignore[return-value]


class TemplateUpdate(BaseModel):
    tipo: str | None = Field(default=None, min_length=1, max_length=120)
    nivel: str | None = Field(default=None, min_length=1, max_length=120)
    area_referencia: float | None = Field(default=None, ge=0, le=_AREA_MAX)
    ativo: bool | None = None

    @field_validator("tipo", "nivel")
    @classmethod
    def _v(cls, v: str | None) -> str | None:
        return _texto_limpo(v)


# ---------------- item do template ----------------
class TemplateItemCreate(BaseModel):
    id: uuid.UUID
    servico_id: uuid.UUID
    etapa: str | None = Field(default=None, max_length=200)
    por_area: bool = False
    fator: float = Field(default=1, ge=0, le=_FATOR_MAX)
    ordem: int = 0


class TemplateItemUpdate(BaseModel):
    etapa: str | None = Field(default=None, max_length=200)
    por_area: bool | None = None
    fator: float | None = Field(default=None, ge=0, le=_FATOR_MAX)
    ordem: int | None = None


class TemplateItemOut(BaseModel):
    id: uuid.UUID
    servico_id: uuid.UUID
    descricao: str                       # do catálogo (join)
    unidade: str | None = None
    custo_mo: float = 0                   # unitário (join) — p/ preview do template
    custo_material: float = 0
    custo_equipamento: float = 0
    etapa: str | None = None
    por_area: bool = False
    fator: float = 1
    ordem: int = 0


# ---------------- saídas ----------------
class TemplateResumoOut(BaseModel):
    id: uuid.UUID
    tipo: str
    nivel: str
    area_referencia: float | None = None
    ativo: bool = True
    n_itens: int = 0
    created_at: dt.datetime
    updated_at: dt.datetime


class TemplateOut(BaseModel):
    id: uuid.UUID
    tipo: str
    nivel: str
    area_referencia: float | None = None
    ativo: bool = True
    created_at: dt.datetime
    updated_at: dt.datetime
    itens: list[TemplateItemOut] = []


# ---------------- aplicar (orçamento) ----------------
class AplicarTemplateIn(BaseModel):
    template_id: uuid.UUID
    ambiente_nome: str = Field(min_length=1, max_length=200)
    area_m2: float | None = Field(default=None, ge=0, le=_AREA_MAX)

    @field_validator("ambiente_nome")
    @classmethod
    def _v(cls, v: str) -> str:
        return _texto_limpo(v)  # type: ignore[return-value]


# ---------------- promover (do orçamento real → template) ----------------
class PromoverTemplateLinha(BaseModel):
    descricao: str = Field(min_length=1, max_length=300)
    unidade: str | None = Field(default=None, max_length=20)
    quantidade: float | None = Field(default=None, ge=0)
    valor_mo: float = Field(default=0, ge=0)
    valor_material: float = Field(default=0, ge=0)
    valor_equipamento: float = Field(default=0, ge=0)
    etapa: str | None = Field(default=None, max_length=200)


class PromoverTemplateIn(BaseModel):
    """Salvar um conjunto de linhas (ex.: um cômodo do orçamento) como template. Cada linha vira um
    serviço no catálogo (merge por nome) + um item do template como QUANTIDADE FIXA (o arquiteto
    marca depois quais escalam por m²). 409 se já existir template com o mesmo tipo×nível."""

    tipo: str = Field(min_length=1, max_length=120)
    nivel: str = Field(min_length=1, max_length=120)
    area_referencia: float | None = Field(default=None, ge=0, le=_AREA_MAX)
    itens: list[PromoverTemplateLinha] = Field(min_length=1)

    @field_validator("tipo", "nivel")
    @classmethod
    def _v(cls, v: str) -> str:
        return _texto_limpo(v)  # type: ignore[return-value]
