"""Schemas do checklist (etapas e itens)."""

import datetime as dt
import re
import uuid
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


def _nome_ambiente_limpo(v: str) -> str:
    """Colapsa whitespace ASCII + trim e rejeita vazio (poka-yoke: nome só-espaços burlaria
    min_length). Mesma classe ASCII do _norm/backfill (determinístico, locale-independente)."""
    v = re.sub(r"[ \t\n\r\f\v]+", " ", v).strip()
    if not v:
        raise ValueError("nome do ambiente não pode ser vazio")
    return v

# Poka-yoke ja no contrato: estado so pode ser um dos 3 valores fixos (= enum public.estado_item).
EstadoItem = Literal["pendente", "em_andamento", "concluido"]


class _CustoIn(BaseModel):
    """Bloco de custo (metragem + orçamento) de QUALQUER nível-folha (etapa/subetapa/tarefa). O
    service deriva material = quantidade × valor_unitario e total = MO + material (total é
    sobrescrevível: se vier explícito, vale). Todos opcionais."""

    unidade: str | None = Field(default=None, max_length=40)
    quantidade: float | None = None
    valor_unitario: float | None = None  # R$/unidade (material = quantidade × este)
    custo_mao_obra: float | None = None
    custo_material: float | None = None
    custo_total: float | None = None


class EtapaCreate(_CustoIn):
    # id gerado no cliente (offline); tenant_id nunca vem do cliente (é derivado no servidor).
    id: uuid.UUID
    nome: str = Field(min_length=1, max_length=200)
    ordem: int = 0


class NodeDetalhes(_CustoIn):
    """PATCH do bloco de custo de uma ETAPA/SUBETAPA folha (sem subitens). Só o custo (datas e
    conclusão têm rotas próprias). exclude_unset distingue 'não mexer' de 'limpar p/ null'."""


class EtapaRename(BaseModel):
    nome: str = Field(min_length=1, max_length=200)


class EtapaReorder(BaseModel):
    ordem: int


class EtapaConclusao(BaseModel):
    concluida: bool
    # base esperada pelo cliente (offline): se diferir do servidor → 409 (não sobrescreve).
    concluida_de: bool | None = None


# Subetapa = agrupador entre Etapa e Tarefa (espelha os schemas da Etapa, + etapa_id no create).
class SubetapaCreate(_CustoIn):
    id: uuid.UUID  # gerado no cliente (offline)
    etapa_id: uuid.UUID
    nome: str = Field(min_length=1, max_length=200)
    ordem: int = 0


class SubetapaRename(BaseModel):
    nome: str = Field(min_length=1, max_length=200)


class SubetapaReorder(BaseModel):
    ordem: int


class SubetapaConclusao(BaseModel):
    concluida: bool
    concluida_de: bool | None = None


class ItemCreate(_CustoIn):
    id: uuid.UUID  # gerado no cliente (offline)
    etapa_id: uuid.UUID
    # setado = Tarefa pertence a esta SUBETAPA (mesma etapa); None = direto na etapa. Só em tarefa
    # top-level; numa SubTarefa repete o subetapa_id do pai (o guard valida).
    subetapa_id: uuid.UUID | None = None
    # quando setado, cria um SUB-ITEM (filho) dessa tarefa-pai; None = tarefa top-level da etapa.
    parent_item_id: uuid.UUID | None = None
    nome: str = Field(min_length=1, max_length=300)
    ordem: int = 0
    # cômodo p/ agrupar (o orçamento vem do _CustoIn). Opcional.
    ambiente: str | None = Field(default=None, max_length=120)


class ItemRename(BaseModel):
    nome: str = Field(min_length=1, max_length=300)


class ItemDetalhes(_CustoIn):
    """PATCH parcial de ambiente/orçamento/equipe (só arquiteto). exclude_unset distingue
    'não mexer' de 'limpar p/ null' — o service aplica apenas os campos enviados. Custo vem do
    _CustoIn (unidade/quantidade/valor_unitario/MO/material/total)."""

    ambiente: str | None = Field(default=None, max_length=120)
    equipe_id: uuid.UUID | None = None  # equipe responsável (biblioteca nível-tenant); None = sem


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
    tipo: Literal["item", "etapa", "subetapa"]
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


class AmbienteCreate(BaseModel):
    # id gerado no cliente (offline); tenant_id derivado no servidor.
    id: uuid.UUID
    nome: str = Field(min_length=1, max_length=120)
    # le = teto do numeric(10,2) no banco → 422 limpo em vez de 500 por overflow (22003).
    area_m2: float | None = Field(default=None, ge=0, le=99_999_999.99)

    @field_validator("nome")
    @classmethod
    def _limpa_nome(cls, v: str) -> str:
        return _nome_ambiente_limpo(v)


class AmbienteUpdate(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=120)
    area_m2: float | None = Field(default=None, ge=0, le=99_999_999.99)

    @field_validator("nome")
    @classmethod
    def _limpa_nome(cls, v: str | None) -> str | None:
        return _nome_ambiente_limpo(v) if v is not None else v


class AmbientesReorder(BaseModel):
    """Reordena os ambientes da obra: a posição na lista vira a `ordem` (0,1,2…)."""

    ids: list[uuid.UUID] = Field(default_factory=list, max_length=2000)


class AmbienteOut(BaseModel):
    id: uuid.UUID
    nome: str
    ordem: int
    area_m2: float | None = None


class ItemOut(BaseModel):
    id: uuid.UUID
    etapa_id: uuid.UUID
    # subetapa à qual a Tarefa pertence (None = direto na etapa). SubTarefa herda o do pai.
    subetapa_id: uuid.UUID | None = None
    parent_item_id: uuid.UUID | None = None
    nome: str
    estado: str
    # avanço parcial da FOLHA (0..100), mantido pelas medições do diário; null = sem medição → o
    # front cai no estado (concluido=100, senão 0). Em agregador é null (o front deriva dos filhos).
    progresso_pct: float | None = None
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
    ambiente: str | None = None  # nome denormalizado (display/PDF/CSV); registro em ambiente_id
    ambiente_id: uuid.UUID | None = None
    equipe_id: uuid.UUID | None = None  # equipe responsável (cor/filtro no Gantt; tenant)
    unidade: str | None = None
    quantidade: float | None = None
    valor_unitario: float | None = None  # R$/unidade (material = quantidade × este)
    custo_mao_obra: float | None = None
    custo_material: float | None = None
    custo_total: float | None = None
    # eh_folha = não tem sub-itens. A FOLHA carrega o trabalho real (estado/datas/duração/custo/
    # dependências); um item AGREGADOR (com sub-itens) tem datas DERIVADAS (min/max dos filhos).
    eh_folha: bool = True
    # sub-itens (filhos manuais). Só preenchidos nas tarefas com filhos (etapa/subetapa→tarefa→sub).
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
    # bloco de custo: só quando a etapa é FOLHA (sem subetapa/tarefa); senão é null (agregador). O
    # front faz o rollup recursivo somando as folhas. Oculto p/ prestador (mascarado no get_tree).
    unidade: str | None = None
    quantidade: float | None = None
    valor_unitario: float | None = None
    custo_mao_obra: float | None = None
    custo_material: float | None = None
    custo_total: float | None = None


class SubetapaOut(BaseModel):
    id: uuid.UUID
    etapa_id: uuid.UUID
    nome: str
    ordem: int
    seq_humano: int | None = None
    updated_at: dt.datetime
    # datas EFETIVAS: min/max das tarefas; se não tem tarefas, as datas próprias (marco-folha).
    data_inicio: dt.date | None = None
    data_fim: dt.date | None = None
    # true quando a subetapa não tem tarefas → o front deixa editar datas/conclusão direto nela.
    sem_itens: bool = False
    concluida: bool = False
    concluida_em: dt.datetime | None = None
    # bloco de custo: só quando a subetapa é FOLHA (sem tarefa); senão null (agregador). Oculto p/
    # prestador (mascarado no get_tree).
    unidade: str | None = None
    quantidade: float | None = None
    valor_unitario: float | None = None
    custo_mao_obra: float | None = None
    custo_material: float | None = None
    custo_total: float | None = None


class SubetapaTreeOut(SubetapaOut):
    itens: list[ItemOut] = []  # tarefas top-level desta subetapa


class EtapaTreeOut(EtapaOut):
    subetapas: list[SubetapaTreeOut] = []  # agrupadores (4º nível)
    itens: list[ItemOut] = []              # tarefas DIRETO na etapa (subetapa_id NULL; ragged)


class ChecklistTreeOut(BaseModel):
    obra_id: uuid.UUID
    etapas: list[EtapaTreeOut] = []
    dependencias: list[DepOut] = []
    ambientes: list[AmbienteOut] = []


class ImportResumoOut(BaseModel):
    etapas_novas: int
    etapas_existentes: int
    itens_novos: int
    itens_existentes: int
