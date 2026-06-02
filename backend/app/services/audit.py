"""Serviço de auditoria — gravação centralizada via a função SECURITY DEFINER cria_audit_log.

Grava na MESMA transação da mutação de domínio. O snapshot legível (entity_label/entity_seq/
actor_label) é CONGELADO no momento do evento — nunca re-hidratar via JOIN ao vivo.
"""

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def log_event(
    session: AsyncSession,
    *,
    tenant,
    actor_id,
    obra_id,
    action: str,
    entity_type: str,
    entity_id,
    entity_label: str,
    entity_seq: int | None = None,
    actor_label: str | None = None,
    changed: dict | None = None,
) -> None:
    await session.execute(
        text(
            """
            select public.cria_audit_log(
                cast(:tenant as uuid), cast(:actor as uuid), cast(:obra as uuid),
                :action, :etype, cast(:eid as uuid), cast(:changed as jsonb),
                :elabel, :eseq, :alabel)
            """
        ),
        {
            "tenant": str(tenant) if tenant is not None else None,
            "actor": str(actor_id) if actor_id is not None else None,
            "obra": str(obra_id) if obra_id is not None else None,
            "action": action,
            "etype": entity_type,
            "eid": str(entity_id),
            "changed": json.dumps(changed) if changed is not None else None,
            "elabel": entity_label,
            "eseq": entity_seq,
            "alabel": actor_label,
        },
    )
