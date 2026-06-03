"""Schemas do estoque (NF-e): notas + itens + conferência + saldo."""

import datetime as dt
import uuid

from pydantic import BaseModel, Field


class NotaItemOut(BaseModel):
    id: uuid.UUID
    codigo: str | None = None
    descricao: str  # nome fiel ao XML
    nome_editado: str | None = None
    nome: str  # coalesce(nome_editado, descricao) — o que a UI mostra
    ncm: str | None = None
    unidade: str | None = None
    quantidade_nota: float
    valor_unitario: float | None = None
    valor_total: float | None = None
    quantidade_conferida: float | None = None  # None = ainda não conferido
    conferido_por: uuid.UUID | None = None
    conferido_por_nome: str | None = None
    conferido_em: dt.datetime | None = None
    divergente: bool = False  # conferida != qtd da nota
    ordem: int
    created_at: dt.datetime


class NotaResumoOut(BaseModel):
    id: uuid.UUID
    seq_humano: int | None = None
    numero: str | None = None
    serie: str | None = None
    chave_acesso: str | None = None
    emitente_nome: str | None = None
    emitente_cnpj: str | None = None
    data_emissao: dt.datetime | None = None
    data_chegada: dt.date | None = None
    valor_total: float
    total_itens: int
    itens_conferidos: int
    itens_divergentes: int
    created_at: dt.datetime


class NotaDetalheOut(NotaResumoOut):
    itens: list[NotaItemOut] = []


class NotaUpdate(BaseModel):
    # data de chegada manual (≠ emissão). None = limpar.
    data_chegada: dt.date | None = None


class ItemNomeUpdate(BaseModel):
    nome_editado: str | None = Field(default=None, max_length=300)


class ConferenciaIn(BaseModel):
    # qtd contada na obra. None = desfazer a conferência.
    quantidade_conferida: float | None = Field(default=None, ge=0)


class ImportResumoNotaOut(BaseModel):
    nota_id: uuid.UUID
    criada: bool  # False = já existia (idempotente pela chave)
    itens_novos: int


class SaldoItemOut(BaseModel):
    nome: str
    unidade: str | None = None
    fornecedor: str | None = None  # emitente da NF-e (o saldo agrupa por produto + fornecedor)
    notas: str | None = None  # número(s) da(s) NF-e de origem (ex.: "6170" ou "6170, 6201")
    data_chegada: dt.date | None = None  # chegada mais recente do grupo (se preenchida)
    quantidade_total: float  # soma de (conferida ?? qtd da nota)
    valor_total: float
