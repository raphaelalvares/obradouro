"""Schemas do checklist (etapas e itens)."""

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, Field

# Poka-yoke ja no contrato: estado so pode ser um dos 3 valores fixos (= enum public.estado_item).
EstadoItem = Literal["pendente", "em_andamento", "concluido"]


class EtapaCreate(BaseModel):
    # id gerado no cliente (offline); tenant_id nunca vem do cliente (é derivado no servidor).
    id: uuid.UUID
    nome: str = Field(min_length=1, max_length=200)
    ordem: int = 0


class EtapaRename(BaseModel):
    nome: str = Field(min_length=1, max_length=200)


class EtapaReorder(BaseModel):
    ordem: int


class ItemCreate(BaseModel):
    id: uuid.UUID  # gerado no cliente (offline)
    etapa_id: uuid.UUID
    nome: str = Field(min_length=1, max_length=300)
    ordem: int = 0


class ItemRename(BaseModel):
    nome: str = Field(min_length=1, max_length=300)


class ItemEstado(BaseModel):
    estado: EstadoItem
    # base esperada pelo cliente (offline): se diferir do servidor -> 409 (não sobrescreve).
    estado_de: EstadoItem | None = None


class ItemOut(BaseModel):
    id: uuid.UUID
    etapa_id: uuid.UUID
    nome: str
    estado: str
    concluido_por: uuid.UUID | None = None
    concluido_por_nome: str | None = None
    concluido_em: dt.datetime | None = None
    ordem: int
    seq_humano: int | None = None
    updated_at: dt.datetime


class EtapaOut(BaseModel):
    id: uuid.UUID
    nome: str
    ordem: int
    seq_humano: int | None = None
    updated_at: dt.datetime


class EtapaTreeOut(EtapaOut):
    itens: list[ItemOut] = []


class ChecklistTreeOut(BaseModel):
    obra_id: uuid.UUID
    etapas: list[EtapaTreeOut] = []


class ImportResumoOut(BaseModel):
    etapas_novas: int
    etapas_existentes: int
    itens_novos: int
    itens_existentes: int
