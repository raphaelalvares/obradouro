"""Schemas do módulo de Orçamento (dentro de Projeto).

Versão = snapshot (R0, R1…); a não-congelada é a editável. Custo por linha = UNITÁRIO em 3 baldes
(M.O/material/equip.); subtotal da linha = valor × quantidade (0068). Percentuais (majoração por
tipo, BDI, imposto) são globais por versão. Totais calculados no backend (não persistidos):
  Preço = [Σ (unit_tipo × qtd) × (1 + majoração_tipo/100)] × (1 + BDI/100) × (1 + Imposto/100).
"""

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, Field


class CriarVersaoIn(BaseModel):
    id: uuid.UUID  # id da NOVA versão, gerado no cliente (dual-ID)


class ItemCreate(BaseModel):
    id: uuid.UUID  # gerado no cliente
    etapa: str = Field(min_length=1, max_length=200)
    descricao: str = Field(min_length=1, max_length=300)
    ordem_etapa: int = 0
    ordem: int = 0
    ambiente: str | None = Field(default=None, max_length=200)  # cômodo (None = obra geral)
    unidade: str | None = Field(default=None, max_length=20)
    quantidade: float | None = Field(default=None, ge=0)
    valor_mo: float = Field(default=0, ge=0)           # UNITÁRIO (subtotal = valor × qtd)
    valor_material: float = Field(default=0, ge=0)     # UNITÁRIO
    valor_equipamento: float = Field(default=0, ge=0)  # UNITÁRIO


class ItemUpdate(BaseModel):
    """PATCH parcial do item (exclude_unset)."""

    etapa: str | None = Field(default=None, min_length=1, max_length=200)
    descricao: str | None = Field(default=None, min_length=1, max_length=300)
    ordem_etapa: int | None = None
    ordem: int | None = None
    ambiente: str | None = Field(default=None, max_length=200)
    unidade: str | None = Field(default=None, max_length=20)
    quantidade: float | None = Field(default=None, ge=0)
    valor_mo: float | None = Field(default=None, ge=0)
    valor_material: float | None = Field(default=None, ge=0)
    valor_equipamento: float | None = Field(default=None, ge=0)


class VersaoParams(BaseModel):
    """PATCH parcial dos parâmetros da versão editável (exclude_unset)."""

    data: dt.date | None = None
    validade: dt.date | None = None
    enviado: bool | None = None
    maj_mo: float | None = Field(default=None, ge=0)
    maj_material: float | None = Field(default=None, ge=0)
    maj_equipamento: float | None = Field(default=None, ge=0)
    bdi: float | None = Field(default=None, ge=0)
    imposto: float | None = Field(default=None, ge=0)
    observacoes: str | None = Field(default=None, max_length=4000)


class ItemOut(BaseModel):
    id: uuid.UUID
    etapa: str
    ordem_etapa: int
    descricao: str
    ordem: int
    ambiente: str | None = None
    unidade: str | None = None
    quantidade: float | None = None
    valor_mo: float = 0
    valor_material: float = 0
    valor_equipamento: float = 0


class TotaisOut(BaseModel):
    # bases (cruas) e majoradas por tipo
    base_mo: float = 0
    base_material: float = 0
    base_equipamento: float = 0
    mo: float = 0
    material: float = 0
    equipamento: float = 0
    custo_direto: float = 0  # soma dos 3 baldes majorados
    bdi_valor: float = 0
    imposto_valor: float = 0
    preco_final: float = 0


class EtapaGrupoOut(BaseModel):
    etapa: str
    ordem_etapa: int
    custo_direto: float = 0  # soma majorada da etapa (sem BDI/imposto)
    itens: list[ItemOut] = []


class AmbienteGrupoOut(BaseModel):
    """Pivot por cômodo (vista 'por cômodo'). ambiente=None → 'Geral' (obra, sem cômodo)."""

    ambiente: str | None = None
    custo_direto: float = 0  # soma majorada do cômodo (sem BDI/imposto)
    itens: list[ItemOut] = []


class OrcamentoVersaoOut(BaseModel):
    id: uuid.UUID
    numero: int
    congelado: bool
    data: dt.date | None = None
    validade: dt.date | None = None
    enviado: bool = False
    enviado_em: dt.datetime | None = None
    maj_mo: float = 0
    maj_material: float = 0
    maj_equipamento: float = 0
    bdi: float = 0
    imposto: float = 0
    observacoes: str | None = None
    decisao: str | None = None  # null = pendente; aprovado/alteracao_pedida/recusado
    decisao_motivo: str | None = None
    decidido_em: dt.datetime | None = None
    seq_humano: int | None = None
    created_at: dt.datetime
    updated_at: dt.datetime
    totais: TotaisOut
    etapas: list[EtapaGrupoOut] = []
    ambientes: list[AmbienteGrupoOut] = []  # mesmo conteúdo, agrupado por cômodo (vista alterna)


class VersaoResumoOut(BaseModel):
    """Item da lista de versões (histórico) — sem os itens, só o resumo."""

    id: uuid.UUID
    numero: int
    congelado: bool
    enviado: bool = False
    decisao: str | None = None  # null = pendente
    data: dt.date | None = None
    validade: dt.date | None = None
    seq_humano: int | None = None
    created_at: dt.datetime
    custo_direto: float = 0
    preco_final: float = 0


class PropostaItemOut(BaseModel):
    """Linha da PROPOSTA (visão do cliente/PDF): só o preço de VENDA — nunca custos por balde
    nem majoração/BDI/imposto."""

    descricao: str
    ambiente: str | None = None
    unidade: str | None = None
    quantidade: float | None = None
    valor: float = 0  # preço de venda da linha (Σ das linhas = preco_final)


class PropostaEtapaOut(BaseModel):
    etapa: str
    valor: float = 0  # preço de venda da etapa
    itens: list[PropostaItemOut] = []


class PropostaResumoOut(BaseModel):
    """Item da lista de propostas do portal (versões ENVIADAS)."""

    id: uuid.UUID
    numero: int
    data: dt.date | None = None
    validade: dt.date | None = None
    enviado_em: dt.datetime | None = None
    decisao: str | None = None  # null = pendente; aprovado/alteracao_pedida/recusado
    decidido_em: dt.datetime | None = None
    preco_final: float = 0


class PropostaOut(PropostaResumoOut):
    """Proposta completa (portal do cliente). Visão de VENDA da versão enviada."""

    observacoes: str | None = None
    decisao_motivo: str | None = None
    projeto_nome: str | None = None
    etapas: list[PropostaEtapaOut] = []


class DecidirIn(BaseModel):
    """Decisão do cliente sobre a proposta (portal). motivo obrigatório p/ recusa/alteração."""

    acao: Literal["aprovado", "alteracao_pedida", "recusado"]
    motivo: str | None = Field(default=None, max_length=2000)


class VirarObraIn(BaseModel):
    """id da obra NOVA (dual-ID, gerado no cliente). Ignorado se o projeto já tem obra vinculada."""

    obra_id: uuid.UUID


class VirarObraOut(BaseModel):
    obra_id: uuid.UUID
    obra_nome: str
    obra_seq: int | None = None
    obra_criada: bool = False  # false = semeou a obra já vinculada ao projeto
    etapas_novas: int = 0
    etapas_existentes: int = 0
    itens_novos: int = 0
    itens_existentes: int = 0


class OrcamentoCentralOut(BaseModel):
    """Linha da CENTRAL de orçamentos (cross-projeto): 1 por projeto do arquiteto, com a versão
    EDITÁVEL (atual) + total. tem_orcamento=false → projeto ainda sem nenhuma versão."""

    projeto_id: uuid.UUID
    projeto_nome: str
    projeto_seq: int | None = None
    tem_orcamento: bool = False
    versao_id: uuid.UUID | None = None
    numero: int | None = None
    versao_seq: int | None = None
    enviado: bool = False
    data: dt.date | None = None
    validade: dt.date | None = None
    atualizado_em: dt.datetime | None = None
    n_versoes: int = 0
    custo_direto: float = 0
    preco_final: float = 0
