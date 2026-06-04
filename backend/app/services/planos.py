"""Serviço de plano/quota: estado 100% derivado (nunca dessincroniza)."""

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def tem_flag(session: AsyncSession, eixo: str, tenant_id: str | None = None) -> bool:
    """Flag booleana de funcionalidade do plano (ex.: 'export_pdf', 'logo'). tenant_id=None usa o
    usuário corrente; passe o tenant de OUTRO arquiteto (ex.: dono da obra no PDF gerado por
    cliente/prestador) para checar a flag DELE. Lê via public.plano_flag (SECURITY DEFINER)."""
    if tenant_id is None:
        row = await session.execute(
            text("select public.plano_flag((select auth.uid()), :k)"), {"k": eixo}
        )
    else:
        row = await session.execute(
            text("select public.plano_flag(cast(:t as uuid), :k)"),
            {"t": str(tenant_id), "k": eixo},
        )
    return bool(row.scalar())


async def get_quota(session: AsyncSession) -> dict:
    row = (
        await session.execute(
            text(
                """
                select pt.codigo as plano,
                       coalesce((pt.limites ->> 'obras_ativas')::bigint, 0) as limite,
                       coalesce((pt.limites ->> 'armazenamento_mb')::bigint, 0) as armaz_mb,
                       (select count(*) from public.obras o
                          where o.tenant_id = (select auth.uid()) and o.status = 'ativa') as em_uso,
                       public.meu_consumo_armazenamento_bytes() as armaz_usado,
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
            "armazenamento": {"usado_bytes": 0, "limite_mb": 0},
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
        "armazenamento": {"usado_bytes": int(row.armaz_usado), "limite_mb": int(row.armaz_mb)},
        "pode_criar_obra": limite < 0 or em_uso < limite,
        "flags": flags or {},
    }
