"""Geração do PDF do checklist (Fase 7 — feature premium 'export_pdf').

Orquestra: autoriza (membro da obra) → checa a flag do plano do DONO da obra → carrega a árvore +
a marca → delega a montagem dos bytes ao renderizador puro (pdf_render). Qualquer membro pode
exportar (cliente quer imprimir também); a flag é do tenant da obra, então reflete "esta obra é de
uma conta Pro". O logo só entra se a flag 'logo' também estiver ligada para esse tenant.
"""

import datetime as dt
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.problems import FeatureBloqueadaError
from app.services import planos as planos_svc
from app.services.checklist import get_tree
from app.services.common import obra_member
from app.services.pdf_render import render_checklist_pdf
from app.services.storage import get_storage

_DETALHE_PDF = "A exportação do checklist em PDF está disponível no plano Pro."


async def gerar_pdf(session: AsyncSession, obra_id: uuid.UUID) -> bytes:
    cur = await obra_member(session, obra_id)  # 404 se não-membro; qualquer papel pode exportar
    if not await planos_svc.tem_flag(session, "export_pdf", cur.tenant_id):
        raise FeatureBloqueadaError("export_pdf", _DETALHE_PDF)

    tree = await get_tree(session, obra_id)

    # marca do tenant da obra (pode não ser o usuário corrente → função SECURITY DEFINER do 0050)
    brow = (
        await session.execute(
            text(
                "select nome_escritorio, logo_key, logo_mime "
                "from public.branding_do_tenant(cast(:t as uuid))"
            ),
            {"t": str(cur.tenant_id)},
        )
    ).first()

    nome_escritorio = brow.nome_escritorio if brow else None
    logo_bytes: bytes | None = None
    if brow and brow.logo_key and await planos_svc.tem_flag(session, "logo", cur.tenant_id):
        try:
            logo_bytes = await get_storage().recuperar(brow.logo_key)
        except FileNotFoundError:
            logo_bytes = None  # logo sumiu do storage: gera o PDF sem ele

    obra = {"nome": cur.nome, "seq_humano": cur.seq_humano}
    gerado_em = dt.datetime.now().strftime("%d/%m/%Y %H:%M")
    return render_checklist_pdf(obra, tree["etapas"], nome_escritorio, logo_bytes, gerado_em)
