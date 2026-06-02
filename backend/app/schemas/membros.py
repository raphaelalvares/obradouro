"""Schemas de membros da obra."""

import datetime as dt
import uuid

from pydantic import BaseModel


class MembroOut(BaseModel):
    id: uuid.UUID
    profile_id: uuid.UUID
    nome: str | None = None
    email: str | None = None
    papel: str
    estado: str
    created_at: dt.datetime
