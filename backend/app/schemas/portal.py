"""Portal do Cliente — pré-autorização de acesso por e-mail + contexto de roteamento.

O arquiteto autoriza um e-mail no projeto/obra (`AcessoClienteCreate`) e define um PRAZO de validade
(`validade_tipo`/`validade_ate`); o cliente se autocadastra e, no 1º login, sincroniza (POST) — isso
materializa os vínculos e devolve o `PortalContextoOut`. No vencimento o acesso é bloqueado (0096):
`expira_em`/`expirado` são derivados.
"""

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, EmailStr, model_validator

ValidadeTipo = Literal["sem_prazo", "data", "entrega"]


class AcessoPrazo(BaseModel):
    """Prazo do acesso: sem prazo, até uma DATA fixa, ou até a ENTREGA da obra."""

    validade_tipo: ValidadeTipo = "sem_prazo"
    validade_ate: dt.date | None = None  # obrigatório só p/ 'data'

    @model_validator(mode="after")
    def _coerente(self):
        if self.validade_tipo == "data":
            if self.validade_ate is None:
                raise ValueError("validade_ate é obrigatório para prazo por data")
            if self.validade_ate < dt.date.today():
                raise ValueError("a data de validade não pode estar no passado")
        else:
            self.validade_ate = None  # 'sem_prazo'/'entrega' não usam data
        return self


class AcessoClienteCreate(AcessoPrazo):
    email: EmailStr  # papel fixo = cliente (escopo projeto+obra)


class AcessoClienteOut(BaseModel):
    id: uuid.UUID
    email: str
    estado: str  # 'pendente' (e-mail autorizado, ainda não reivindicado) | 'ativo' (vinculado)
    cadastrado: bool  # já entrou (vínculo materializado) — status legível na lista do arquiteto
    validade_tipo: ValidadeTipo
    validade_ate: dt.date | None = None
    # derivado: data+1 / entrega→entregue_em da obra / sem_prazo→null
    expira_em: dt.datetime | None = None
    expirado: bool = False  # derivado: expira_em já passou (acesso bloqueado)
    projeto_id: uuid.UUID | None = None
    obra_id: uuid.UUID | None = None
    created_at: dt.datetime


class LiberarPortalOut(BaseModel):
    """Resposta do "liberar portal a partir da oportunidade": o e-mail usado (do lead) + se o
    convite foi de fato ENVIADO agora (só na 1ª liberação) + se o cliente já entrou. O front usa
    `convite_enviado` p/ um toast honesto (não dizer "enviado" numa re-liberação idempotente)."""

    email: str
    cadastrado: bool
    convite_enviado: bool


class PortalProjetoOut(BaseModel):
    id: uuid.UUID
    nome: str
    seq_humano: int | None = None
    obra_id: uuid.UUID | None = None


class PortalObraOut(BaseModel):
    id: uuid.UUID
    nome: str
    seq_humano: int | None = None
    status: str | None = None


class PortalContextoOut(BaseModel):
    eh_arquiteto: bool
    eh_cliente: bool
    # tem vínculo de cliente em algum lugar, mesmo VENCIDO (distingue cliente expirado de arquiteto
    # novo): o front roteia o portal por (not eh_arquiteto and tem_papel_cliente).
    tem_papel_cliente: bool = False
    projetos: list[PortalProjetoOut] = []
    obras: list[PortalObraOut] = []
