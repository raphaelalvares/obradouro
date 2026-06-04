"""Schemas do export de dados (Fase 8 — portabilidade LGPD)."""

import datetime as dt
import uuid

from pydantic import BaseModel


class ExportJobOut(BaseModel):
    id: uuid.UUID
    status: str  # pendente | processando | pronto | erro | expirado
    tamanho_bytes: int | None = None
    erro: str | None = None
    pronto_em: dt.datetime | None = None
    expira_em: dt.datetime | None = None
    created_at: dt.datetime
