"""Serviço de plano/quota: estado 100% derivado (nunca dessincroniza)."""

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def get_quota(session: AsyncSession) -> dict:
    row = (
        await session.execute(
            text(
                """
                select pt.codigo as plano,
                       coalesce((pt.limites ->> 'obras_ativas')::bigint, 0) as limite,
                       (select count(*) from public.obras o
                          where o.tenant_id = (select auth.uid()) and o.status = 'ativa') as em_uso,
                       pt.flags as flags
                from public.plano_do_tenant((select auth.uid())) pt
                """
            )
        )
    ).first()
    if row is None:
        # sem perfil/plano resolvido — trata como free vazio (não deve acontecer no fluxo normal)
        return {
            "plano": "free",
            "obras_ativas": {"em_uso": 0, "limite": 0},
            "pode_criar_obra": False,
            "flags": {},
        }
    limite = int(row.limite)
    em_uso = int(row.em_uso)
    flags = row.flags
    if isinstance(flags, str):  # asyncpg devolve jsonb como texto
        flags = json.loads(flags)
    return {
        "plano": row.plano,
        "obras_ativas": {"em_uso": em_uso, "limite": limite},
        "pode_criar_obra": limite < 0 or em_uso < limite,
        "flags": flags or {},
    }
