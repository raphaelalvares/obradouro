"""Schemas de convites (por email) e convites pendentes."""

import uuid
from typing import Literal

from pydantic import BaseModel, EmailStr


class ConviteCreate(BaseModel):
    email: EmailStr
    papel: Literal["cliente", "prestador"]


class ConviteEnviadoOut(BaseModel):
    profile_id: uuid.UUID
    estado: str
    # B3: sem action_link — o convite a usuário novo vai pelo email do Supabase (não pela resposta),
    # então a resposta não revela se o email já tinha conta.


class ConvitePendenteOut(BaseModel):
    obra_id: uuid.UUID
    obra_nome: str
    seq_humano: int | None = None
    invited_by_nome: str | None = None


class AceiteOut(BaseModel):
    obra_id: uuid.UUID
    estado: str
