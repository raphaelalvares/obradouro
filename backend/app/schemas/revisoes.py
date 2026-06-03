"""Schemas do ciclo de revisões."""

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, Field

# Poka-yoke: status só os 4 fixos (= enum public.status_revisao).
StatusRevisao = Literal["pendente", "aprovado", "alteracao_pedida", "recusado"]
# Verbos do cliente.
AcaoRevisao = Literal["aprovar", "alteracao", "recusar"]


class RevisaoCreate(BaseModel):
    id: uuid.UUID  # gerado no cliente
    titulo: str | None = Field(default=None, max_length=200)


class RevisaoDecisao(BaseModel):
    acao: AcaoRevisao
    # motivo obrigatório p/ alteração/recusa (validado no service); ignorado em aprovar
    motivo: str | None = Field(default=None, max_length=2000)


class RevisaoArquivoOut(BaseModel):
    id: uuid.UUID
    nome_arquivo: str
    content_type: str
    tamanho_bytes: int
    largura: int | None = None
    altura: int | None = None
    is_pdf: bool = False
    tem_thumb: bool = False
    created_at: dt.datetime


class RevisaoOut(BaseModel):
    id: uuid.UUID
    numero: int  # R0, R1… (numero = nº de alterações; R0 = entrega base)
    titulo: str | None = None
    status: str
    motivo: str | None = None
    decidido_por: uuid.UUID | None = None
    decidido_por_nome: str | None = None
    decidido_em: dt.datetime | None = None
    alem_do_incluido: bool = False  # calculado AO VIVO (numero > revisoes_incluidas)
    seq_humano: int | None = None
    created_at: dt.datetime
    arquivos: list[RevisaoArquivoOut] = []


class ContadorRevisoes(BaseModel):
    controla: bool  # revisoes_incluidas definido (≠ None)
    incluidas: int | None = None  # nº de alterações incluídas (o arquiteto definiu)
    usadas: int  # nº de alterações já feitas (= maior numero do projeto; 0 se só R0 / vazio)
    restantes: int | None = None  # max(0, incluidas - usadas) quando controla
    alem_count: int  # quantas revisões estão além do incluído
