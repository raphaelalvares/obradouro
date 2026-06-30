"""Portal do Cliente — pré-autorização de acesso por e-mail + contexto de roteamento.

O arquiteto autoriza um e-mail no projeto (`AcessoClienteCreate`); o cliente se autocadastra e, no
1º login, `POST /portal/sincronizar` materializa os vínculos e devolve o `PortalContextoOut` (o
front usa `eh_cliente && not eh_arquiteto` p/ mandar o cliente puro pra `/portal`).
"""

import datetime as dt
import uuid

from pydantic import BaseModel, EmailStr


class AcessoClienteCreate(BaseModel):
    email: EmailStr  # papel fixo = cliente (escopo projeto+obra)


class AcessoClienteOut(BaseModel):
    id: uuid.UUID
    email: str
    estado: str  # 'pendente' (e-mail autorizado, ainda não reivindicado) | 'ativo' (vinculado)
    cadastrado: bool  # já existe conta CRIA com esse e-mail (status legível na lista do arquiteto)
    projeto_id: uuid.UUID | None = None
    obra_id: uuid.UUID | None = None
    created_at: dt.datetime


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
    projetos: list[PortalProjetoOut] = []
    obras: list[PortalObraOut] = []
