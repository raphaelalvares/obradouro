"""Geração do cronograma da obra em Excel (.xlsx) — feature premium 'export_pdf' (mesma flag da
impressão em PDF: "exportar é Pro"). Orquestra: autoriza (membro da obra) → checa a flag do plano do
DONO da obra → carrega a árvore + identidade (empresa = marca do escritório; arquiteto = dono) →
delega a montagem dos bytes ao renderizador puro (xlsx_render).
"""

import datetime as dt
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.problems import FeatureBloqueadaError
from app.services import planos as planos_svc
from app.services.checklist import get_tree
from app.services.common import obra_member
from app.services.xlsx_render import render_cronograma_xlsx

_DETALHE = "A exportação do cronograma em Excel está disponível no plano Pro."


async def gerar_xlsx(session: AsyncSession, obra_id: uuid.UUID) -> bytes:
    cur = await obra_member(session, obra_id)  # 404 se não-membro; qualquer papel pode exportar
    if not await planos_svc.tem_flag(session, "export_pdf", cur.tenant_id):
        raise FeatureBloqueadaError("export_pdf", _DETALHE)

    tree = await get_tree(session, obra_id)

    # empresa = nome do escritório do tenant da obra (SECURITY DEFINER do 0050).
    brow = (
        await session.execute(
            text("select nome_escritorio from public.branding_do_tenant(cast(:t as uuid))"),
            {"t": str(cur.tenant_id)},
        )
    ).first()
    empresa = brow.nome_escritorio if brow else None

    # arquiteto = nome do dono (tenant). Co-membro da obra → a RLS de profiles permite ler.
    arow = (
        await session.execute(
            text("select nome from public.profiles where id = cast(:t as uuid)"),
            {"t": str(cur.tenant_id)},
        )
    ).first()
    arquiteto = arow.nome if arow else None

    obra = {"nome": cur.nome, "seq_humano": cur.seq_humano}
    gerado_em = dt.datetime.now().strftime("%d/%m/%Y %H:%M")
    return render_cronograma_xlsx(obra, tree["etapas"], empresa, arquiteto, gerado_em)
