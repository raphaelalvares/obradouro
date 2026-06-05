"""Registro de aceite dos documentos legais (prova versionada — trilha LGPD).

Carimba a versão vigente de cada documento (app.core.legal.DOCUMENTOS) para o usuário corrente,
sob o contexto de RLS da sessão (profile_id = auth.uid()). Idempotente: re-registrar a mesma versão
não duplica (unique profile_id+documento+versao → ON CONFLICT DO NOTHING). `pendentes` diz quais
documentos faltam aceitar na versão vigente (re-aceite quando a versão sobe).
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.legal import DOCUMENTOS

_INSERT = text(
    """insert into public.aceites_legais (profile_id, documento, versao, origem)
       values ((select auth.uid()), :documento, :versao, :origem)
       on conflict (profile_id, documento, versao) do nothing"""
)
_SELECT = text(
    """select documento, versao, origem, aceito_em
       from public.aceites_legais
       where profile_id = (select auth.uid())
       order by aceito_em"""
)
_SELECT_VERSOES = text(
    """select documento, versao
       from public.aceites_legais
       where profile_id = (select auth.uid())"""
)


async def registrar(session: AsyncSession, origem: str | None) -> list[dict]:
    """Registra (idempotente) o aceite da versão vigente de cada documento legal."""
    for documento, versao in DOCUMENTOS.items():
        await session.execute(
            _INSERT, {"documento": documento, "versao": versao, "origem": origem}
        )
    return await listar(session)


async def listar(session: AsyncSession) -> list[dict]:
    rows = (await session.execute(_SELECT)).all()
    return [dict(r._mapping) for r in rows]


async def pendentes(session: AsyncSession) -> list[dict]:
    """Documentos cuja versão VIGENTE o usuário ainda não aceitou (vazio = tudo em dia)."""
    aceitos = {(r.documento, r.versao) for r in (await session.execute(_SELECT_VERSOES)).all()}
    return [
        {"documento": doc, "versao": versao}
        for doc, versao in DOCUMENTOS.items()
        if (doc, versao) not in aceitos
    ]
