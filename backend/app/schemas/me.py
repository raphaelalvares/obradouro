"""Schemas do perfil do usuário corrente."""

import uuid

from pydantic import BaseModel


class ProfileOut(BaseModel):
    id: uuid.UUID
    email: str
    nome: str | None = None
    telefone: str | None = None


class ProfileUpdate(BaseModel):
    nome: str | None = None
    telefone: str | None = None
