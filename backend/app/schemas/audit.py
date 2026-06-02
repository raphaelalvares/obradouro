"""Schemas do audit log (camada de exibição)."""

import datetime as dt
import uuid

from pydantic import BaseModel


class AuditEntryOut(BaseModel):
    id: uuid.UUID
    action: str
    entity_type: str
    entity_id: uuid.UUID
    entity_label: str
    entity_seq: int | None = None
    actor_label: str | None = None
    changed: dict | None = None
    created_at: dt.datetime
