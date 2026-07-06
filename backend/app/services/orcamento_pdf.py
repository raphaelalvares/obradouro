"""Geração do PDF da proposta comercial do orçamento.

Orquestra: autoriza (membro do projeto; não-arquiteto só baixa versão ENVIADA) → resolve o plano do
tenant do projeto → monta a visão de PROPOSTA (preços de VENDA; ver _proposta_etapas) → carrega a
marca (branding_do_tenant + flag 'logo') → delega os bytes ao renderizador puro (pdf_render).
O cliente também pode baixar: o PDF é o documento DELE.

REGRA DE PLANO (não bloqueia o Free — ele precisa enviar a proposta p/ fechar): sem a flag
'export_pdf' (plano Canteiro/Free) o PDF sai COM marca d'água "OBRA D'OURO" e SEM o logo do
escritório; com a flag (Alicerce/Mestre) sai limpo e, se houver flag 'logo', com o logo. Já o PDF/
XLSX do cronograma/checklist seguem 100% bloqueados no Free (ver checklist_pdf/checklist_xlsx).
"""

import datetime as dt
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.concurrency import run_cpu
from app.services import orcamentos as orc_svc
from app.services import planos as planos_svc
from app.services.common import projeto_member
from app.services.orcamento_pdf_render import render_orcamento_pdf
from app.services.storage import get_storage


async def gerar_pdf(
    session: AsyncSession, projeto_id: uuid.UUID, versao_id: uuid.UUID
) -> tuple[bytes, int]:
    """Bytes do PDF + número da revisão (p/ o nome do arquivo). Mesma visão de VENDA do portal:
    get_proposta usa as funções SECURITY DEFINER (0078) → cliente e arquiteto geram PDF idêntico, e
    nenhum custo cru/margem entra aqui (só preço de venda). O arquiteto gera o PDF de qualquer
    versão (precisa dele p/ enviar); o cliente só das ENVIADAS. 404 se não visível a quem pede."""
    cur = await projeto_member(session, projeto_id)  # 404 se não-membro; cliente pode
    # Sem 'export_pdf' (Free) → marca d'água + sem logo; com a flag (Alicerce/Mestre) → limpo. O
    # gate é a flag do tenant DONO do projeto (o cliente baixa o mesmo PDF que o arquiteto gera).
    marca_dagua = not await planos_svc.tem_flag(session, "export_pdf", cur.tenant_id)

    proposta = await orc_svc.get_proposta(session, projeto_id, versao_id)  # 404 se não enviada

    # marca do tenant do projeto (função SECURITY DEFINER do 0050, igual ao PDF do checklist)
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
    # marca d'água nunca leva o logo do escritório (é o diferencial que o upgrade libera)
    if (
        not marca_dagua
        and brow
        and brow.logo_key
        and await planos_svc.tem_flag(session, "logo", cur.tenant_id)
    ):
        try:
            logo_bytes = await get_storage().recuperar(brow.logo_key)
        except FileNotFoundError:
            logo_bytes = None  # logo sumiu do storage: gera o PDF sem ele

    gerado_em = dt.datetime.now().strftime("%d/%m/%Y %H:%M")
    pdf_bytes = await run_cpu(
        render_orcamento_pdf, proposta, nome_escritorio, logo_bytes, gerado_em, marca_dagua
    )
    return (pdf_bytes, proposta["numero"])
