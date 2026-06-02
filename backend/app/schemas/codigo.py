"""Schemas do código de obra."""

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel


class CodigoCreate(BaseModel):
    papel: Literal["cliente", "prestador"]


class CodigoOut(BaseModel):
    codigo: str
    papel: str
    expires_at: dt.datetime


class ResgatarCodigo(BaseModel):
    codigo: str


class ResgateOut(BaseModel):
    obra_id: uuid.UUID
