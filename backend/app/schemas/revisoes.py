"""Schemas do ciclo de revisões."""

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, Field, model_validator

# Poka-yoke: status só os 4 fixos (= enum public.status_revisao).
StatusRevisao = Literal["pendente", "aprovado", "alteracao_pedida", "recusado"]
# Verbos do cliente. "escolher" = aprovar escolhendo 1 das opções de layout (revisão de opções).
AcaoRevisao = Literal["aprovar", "alteracao", "recusar", "escolher"]


class RevisaoCreate(BaseModel):
    id: uuid.UUID  # gerado no cliente
    titulo: str | None = Field(default=None, max_length=200)


class RevisaoDecisao(BaseModel):
    acao: AcaoRevisao
    # motivo obrigatório p/ alteração/recusa (validado no service); ignorado em aprovar/escolher
    motivo: str | None = Field(default=None, max_length=2000)
    # opção do layout escolhido (1..9); só na ação "escolher" (revisão de opções)
    opcao_escolhida: int | None = Field(default=None, ge=1, le=9)

    @model_validator(mode="after")
    def _coerencia_opcao(self) -> "RevisaoDecisao":
        if self.acao == "escolher":
            if self.opcao_escolhida is None:
                raise ValueError("informe a opção escolhida")
        elif self.opcao_escolhida is not None:
            raise ValueError("opção escolhida só se aplica à ação 'escolher'")
        return self


class RevisaoArquivoOut(BaseModel):
    id: uuid.UUID
    nome_arquivo: str
    content_type: str
    tamanho_bytes: int
    largura: int | None = None
    altura: int | None = None
    is_pdf: bool = False
    tem_thumb: bool = False
    opcao: int | None = None  # 1..9 quando a revisão traz opções de layout; null = sem opção
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
    opcao_escolhida: int | None = None  # opção de layout que o cliente escolheu (revisão de opções)
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
