"""Pipeline do projeto — a linha do tempo de 9 etapas fixas que o cliente acompanha no portal.

A espinha vive em `projeto_etapas` (migration 0097). Os GATES de decisão não são reimplementados: a
etapa só aponta pro que já existe (Revisões / Proposta / decidir_iniciar_obra). `acao_pendente` é
derivado do estado vivo (revisão pendente, orçamento enviado-pendente, etc.).
"""

import datetime as dt
from typing import Literal

from pydantic import BaseModel

StatusEtapa = Literal["a_fazer", "em_andamento", "aguardando_cliente", "concluida"]


class EtapaProjetoOut(BaseModel):
    etapa: str
    rotulo: str
    ordem: int
    status: StatusEtapa
    data_prevista: dt.date | None = None
    concluida_em: dt.datetime | None = None
    decisao: str | None = None  # só iniciar_obra: 'sim' | 'nao'
    observacao: str | None = None
    gate: Literal["revisao", "proposta", "iniciar_obra"] | None = None
    acao_pendente: bool = False  # há uma ação do cliente esperando neste gate


class PipelineOut(BaseModel):
    etapas: list[EtapaProjetoOut] = []
    etapa_atual: str | None = None  # 1ª etapa não concluída (foco da timeline)


class EtapaUpdate(BaseModel):
    """Arquiteto avança a etapa (qualquer campo ausente = inalterado)."""

    status: StatusEtapa | None = None
    data_prevista: dt.date | None = None
    observacao: str | None = None


class IniciarObraDecisao(BaseModel):
    decisao: Literal["sim", "nao"]
