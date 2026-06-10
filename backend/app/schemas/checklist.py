"""Schemas do checklist (etapas e itens)."""

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, Field, model_validator

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


class EtapaConclusao(BaseModel):
    concluida: bool
    # base esperada pelo cliente (offline): se diferir do servidor → 409 (não sobrescreve).
    concluida_de: bool | None = None


class ItemCreate(BaseModel):
    id: uuid.UUID  # gerado no cliente (offline)
    etapa_id: uuid.UUID
    # quando setado, cria um SUB-ITEM (filho) dessa tarefa-pai; None = tarefa top-level da etapa.
    parent_item_id: uuid.UUID | None = None
    nome: str = Field(min_length=1, max_length=300)
    ordem: int = 0
    # opcionais: cômodo p/ agrupar + campos de orçamento (mesmos que o import preenche).
    ambiente: str | None = Field(default=None, max_length=120)
    unidade: str | None = Field(default=None, max_length=40)
    quantidade: float | None = None
    custo_mao_obra: float | None = None
    custo_material: float | None = None
    custo_total: float | None = None


class ItemRename(BaseModel):
    nome: str = Field(min_length=1, max_length=300)


class ItemDetalhes(BaseModel):
    """PATCH parcial de ambiente/orçamento (só arquiteto). exclude_unset distingue
    'não mexer' de 'limpar p/ null' — o service aplica apenas os campos enviados."""

    ambiente: str | None = Field(default=None, max_length=120)
    unidade: str | None = Field(default=None, max_length=40)
    quantidade: float | None = None
    custo_mao_obra: float | None = None
    custo_material: float | None = None
    custo_total: float | None = None


class ItemEstado(BaseModel):
    estado: EstadoItem
    # base esperada pelo cliente (offline): se diferir do servidor -> 409 (não sobrescreve).
    estado_de: EstadoItem | None = None


def _valida_intervalo(inicio: dt.date | None, fim: dt.date | None) -> None:
    if inicio is not None and fim is not None and fim < inicio:
        raise ValueError("data_fim não pode ser anterior a data_inicio")


class DatasIn(BaseModel):
    """Datas de cronograma (item ou etapa-sem-itens). Define o intervalo; ambas nulas = limpa."""

    data_inicio: dt.date | None = None
    data_fim: dt.date | None = None

    @model_validator(mode="after")
    def _check(self) -> "DatasIn":
        _valida_intervalo(self.data_inicio, self.data_fim)
        return self


class CronogramaEntrada(BaseModel):
    tipo: Literal["item", "etapa"]
    id: uuid.UUID
    data_inicio: dt.date | None = None
    data_fim: dt.date | None = None

    @model_validator(mode="after")
    def _check(self) -> "CronogramaEntrada":
        _valida_intervalo(self.data_inicio, self.data_fim)
        return self


class CronogramaAplicarIn(BaseModel):
    """Aplica o resultado do 'cronograma macro' (prévia editada) em lote, numa transação só."""

    obra_data_inicio: dt.date | None = None
    obra_data_fim: dt.date | None = None
    entradas: list[CronogramaEntrada] = Field(default_factory=list, max_length=5000)


class ItemDuracaoIn(BaseModel):
    """Duração desejada da tarefa (dias corridos, inclusiva). None = limpa (usa o span/1 dia)."""

    duracao_dias: int | None = Field(default=None, ge=1, le=3650)


class DepCreate(BaseModel):
    # id gerado no cliente (offline); tenant_id derivado no servidor.
    id: uuid.UUID
    predecessora_id: uuid.UUID
    sucessora_id: uuid.UUID
    # v1 implementa SÓ FS (terminar→iniciar); a coluna aceita os 4 p/ futuro, mas a API recusa o que
    # ainda não é calculado (recálculo e bloqueio assumem FS).
    tipo: Literal["FS"] = "FS"
    lag_dias: int = Field(default=0, ge=0, le=3650)  # folga em dias (corridos); sem lead negativo


class DepUpdate(BaseModel):
    tipo: Literal["FS"] | None = None
    lag_dias: int | None = Field(default=None, ge=0, le=3650)


class DepOut(BaseModel):
    id: uuid.UUID
    predecessora_id: uuid.UUID
    sucessora_id: uuid.UUID
    tipo: str
    lag_dias: int


class RecalcularIn(BaseModel):
    """Recálculo automático: âncora opcional (senão obras.data_inicio → min das tarefas da rede)."""

    data_inicio: dt.date | None = None


class ItemOut(BaseModel):
    id: uuid.UUID
    etapa_id: uuid.UUID
    parent_item_id: uuid.UUID | None = None
    nome: str
    estado: str
    concluido_por: uuid.UUID | None = None
    concluido_por_nome: str | None = None
    concluido_em: dt.datetime | None = None
    ordem: int
    seq_humano: int | None = None
    updated_at: dt.datetime
    # cronograma (dias corridos, sem hora)
    data_inicio: dt.date | None = None
    data_fim: dt.date | None = None
    duracao_dias: int | None = None
    # dependências (só nas tarefas top-level): bloqueada = tem predecessor não-concluído;
    # aguarda = seq_humano dos predecessores que faltam concluir. ATENÇÃO: derivados SÓ no get_tree
    # (via _marcar_bloqueio); respostas de PATCH (_get_item) devolvem os defaults — o front sempre
    # invalida/refaz a árvore, então não confie nesses campos no retorno de uma mutação isolada.
    bloqueada: bool = False
    aguarda: list[int] = []
    # cômodo (agrupamento) + orçamento (do import ou manual). Opcionais.
    ambiente: str | None = None
    unidade: str | None = None
    quantidade: float | None = None
    custo_mao_obra: float | None = None
    custo_material: float | None = None
    custo_total: float | None = None
    # sub-itens (filhos manuais). Só preenchidos nas tarefas top-level (3º nível etapa→tarefa→sub).
    subitens: list["ItemOut"] = []


class EtapaOut(BaseModel):
    id: uuid.UUID
    nome: str
    ordem: int
    seq_humano: int | None = None
    updated_at: dt.datetime
    # datas EFETIVAS da etapa: min/max das datas dos itens; se não tem itens, as datas próprias.
    data_inicio: dt.date | None = None
    data_fim: dt.date | None = None
    # true quando a etapa não tem itens → o front deixa editar as datas direto nela.
    sem_itens: bool = False
    # conclusão direta da etapa (marco): p/ etapas SEM tarefas, que não têm checklist p/ derivar.
    concluida: bool = False
    concluida_em: dt.datetime | None = None


class EtapaTreeOut(EtapaOut):
    itens: list[ItemOut] = []


class ChecklistTreeOut(BaseModel):
    obra_id: uuid.UUID
    etapas: list[EtapaTreeOut] = []
    dependencias: list[DepOut] = []


class ImportResumoOut(BaseModel):
    etapas_novas: int
    etapas_existentes: int
    itens_novos: int
    itens_existentes: int
