"""Pipeline do projeto — a linha do tempo de 9 etapas fixas que o cliente acompanha no portal.

A espinha vive em `projeto_etapas` (migration 0097). Os GATES de decisão não são reimplementados: a
etapa só aponta pro que já existe (Revisões / Proposta / decidir_iniciar_obra). `acao_pendente` é
derivado do estado vivo (revisão pendente, orçamento enviado-pendente, etc.).
"""

import datetime as dt
import re
import uuid
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

StatusEtapa = Literal["a_fazer", "em_andamento", "aguardando_cliente", "concluida"]
StatusAprovacao3D = Literal["rascunho", "pendente", "aprovado", "alteracao_pedida"]


def _nome_comodo_limpo(v: str) -> str:
    """Colapsa whitespace ASCII + trim (classe ASCII explícita, ≠ \\s — casa byte-a-byte com o
    backend de ambientes; ver services/ambientes.py)."""
    v = re.sub(r"[ \t\n\r\f\v]+", " ", v or "").strip()
    if not v:
        raise ValueError("nome do cômodo não pode ser vazio")
    return v


class EtapaAnexoOut(BaseModel):
    """Material que o cliente vê numa etapa: ARQUIVO (PDF/imagem) ou LINK (tour 3D, vídeo…)."""

    id: uuid.UUID
    etapa: str
    tipo: Literal["arquivo", "link"]
    label: str | None = None
    url: str | None = None  # tipo='link'
    nome_arquivo: str | None = None  # tipo='arquivo'
    content_type: str | None = None
    tamanho_bytes: int | None = None
    is_pdf: bool = False
    tem_thumb: bool = False
    ordem: int = 0
    created_at: dt.datetime


class EtapaLinkCreate(BaseModel):
    id: uuid.UUID  # gerado no cliente (dual-ID)
    url: str = Field(max_length=2000)
    label: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _valida_url(self) -> "EtapaLinkCreate":
        u = (self.url or "").strip()
        if not (u.startswith("http://") or u.startswith("https://")):
            raise ValueError("o link deve começar com http:// ou https://")
        self.url = u
        return self


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
    anexos: list[EtapaAnexoOut] = []  # material da etapa (arquivos/links curados pelo arquiteto)
    ambientes_3d: list["Ambiente3DOut"] = []  # só na etapa projeto_3d (cômodos + aprovação)
    manual_itens: list["ManualItemOut"] = []  # só na etapa manual (itens por cômodo + anexos)


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


# ==================== 3D / aprovação por ambiente (etapa projeto_3d) ====================
class Ambiente3DOut(BaseModel):
    """Um cômodo do projeto na etapa Projeto 3D: material (renders/links) + estado da aprovação."""

    id: uuid.UUID
    nome: str
    ordem: int
    status_3d: StatusAprovacao3D
    motivo_3d: str | None = None  # preenchido pelo cliente ao pedir alteração
    decidido_por_3d: uuid.UUID | None = None
    decidido_por_nome: str | None = None
    decidido_em: dt.datetime | None = None
    anexos: list[EtapaAnexoOut] = []  # renders/links 3D deste cômodo


class AmbienteProjetoCreate(BaseModel):
    id: uuid.UUID  # gerado no cliente (dual-ID)
    nome: str = Field(min_length=1, max_length=120)

    @field_validator("nome")
    @classmethod
    def _limpa_nome(cls, v: str) -> str:
        return _nome_comodo_limpo(v)


class AmbienteProjetoUpdate(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("nome")
    @classmethod
    def _limpa_nome(cls, v: str | None) -> str | None:
        return _nome_comodo_limpo(v) if v is not None else v


class AmbientesProjetoReorder(BaseModel):
    ids: list[uuid.UUID] = Field(default_factory=list, max_length=2000)


class Aprovacao3DDecisao(BaseModel):
    """Decisão do cliente sobre o 3D de UM cômodo (espelha RevisaoDecisao)."""

    acao: Literal["aprovar", "alteracao"]
    motivo: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _coerencia_motivo(self) -> "Aprovacao3DDecisao":
        if self.acao == "alteracao" and not (self.motivo and self.motivo.strip()):
            raise ValueError("pedir alteração exige um motivo")
        if self.acao == "aprovar" and self.motivo is not None:
            raise ValueError("aprovar não leva motivo")
        return self


# ==================== Manual do proprietário (etapa manual) ====================
def _texto_obrig(v: str) -> str:
    """Colapsa whitespace ASCII + trim; obrigatório (não pode ficar vazio)."""
    v = re.sub(r"[ \t\n\r\f\v]+", " ", v or "").strip()
    if not v:
        raise ValueError("o título do item não pode ser vazio")
    return v


def _texto_opc(v: str | None) -> str | None:
    """Trim de campo opcional; string vazia → None (não guarda lixo)."""
    if v is None:
        return None
    return v.strip() or None


class ManualItemOut(BaseModel):
    """Um item do manual do proprietário: ficha estruturada + anexos (por cômodo ou Geral)."""

    id: uuid.UUID
    ambiente_id: uuid.UUID | None = None  # None = "Geral" (não atrelado a cômodo)
    ambiente_nome: str | None = None
    categoria: str | None = None
    titulo: str
    marca: str | None = None
    modelo: str | None = None
    cor: str | None = None
    fornecedor: str | None = None
    garantia: str | None = None
    observacoes: str | None = None
    ordem: int = 0
    anexos: list[EtapaAnexoOut] = []  # nota fiscal/PDF de garantia/foto/link deste item


class ManualItemCreate(BaseModel):
    id: uuid.UUID  # gerado no cliente (dual-ID)
    ambiente_id: uuid.UUID | None = None
    categoria: str | None = Field(default=None, max_length=80)
    titulo: str = Field(min_length=1, max_length=200)
    marca: str | None = Field(default=None, max_length=200)
    modelo: str | None = Field(default=None, max_length=200)
    cor: str | None = Field(default=None, max_length=200)
    fornecedor: str | None = Field(default=None, max_length=200)
    garantia: str | None = Field(default=None, max_length=2000)
    observacoes: str | None = Field(default=None, max_length=2000)

    @field_validator("titulo")
    @classmethod
    def _limpa_titulo(cls, v: str) -> str:
        return _texto_obrig(v)

    @field_validator("categoria", "marca", "modelo", "cor", "fornecedor", "garantia", "observacoes")
    @classmethod
    def _limpa_opc(cls, v: str | None) -> str | None:
        return _texto_opc(v)


class ManualItemUpdate(BaseModel):
    """Edição do item (full-replace — o diálogo sempre manda todos os campos)."""

    ambiente_id: uuid.UUID | None = None
    categoria: str | None = Field(default=None, max_length=80)
    titulo: str = Field(min_length=1, max_length=200)
    marca: str | None = Field(default=None, max_length=200)
    modelo: str | None = Field(default=None, max_length=200)
    cor: str | None = Field(default=None, max_length=200)
    fornecedor: str | None = Field(default=None, max_length=200)
    garantia: str | None = Field(default=None, max_length=2000)
    observacoes: str | None = Field(default=None, max_length=2000)

    @field_validator("titulo")
    @classmethod
    def _limpa_titulo(cls, v: str) -> str:
        return _texto_obrig(v)

    @field_validator("categoria", "marca", "modelo", "cor", "fornecedor", "garantia", "observacoes")
    @classmethod
    def _limpa_opc(cls, v: str | None) -> str | None:
        return _texto_opc(v)


class ManualItensReorder(BaseModel):
    ids: list[uuid.UUID] = Field(default_factory=list, max_length=2000)


# `EtapaProjetoOut` referencia `Ambiente3DOut`/`ManualItemOut` (acima) por forward-ref → resolve.
EtapaProjetoOut.model_rebuild()
