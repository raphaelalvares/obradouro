"""Rotas do Módulo de Projeto (prefixo /projetos): projeto, vínculo, revisões, moodboard.
No modelo API-only os bytes (arquivos de revisão / itens de moodboard) são servidos pela API com
JWT → o front busca por fetch autenticado e usa blob URL (igual aos anexos)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status

from app.api.deps import CurrentUserId, DbSession
from app.schemas.moodboard import MoodboardItemOut, SecaoCreate, SecaoOut, SecaoUpdate
from app.schemas.orcamentos import (
    CriarVersaoIn,
    OrcamentoVersaoOut,
    VersaoParams,
    VersaoResumoOut,
)
from app.schemas.orcamentos import ItemCreate as OrcItemCreate
from app.schemas.orcamentos import ItemUpdate as OrcItemUpdate
from app.schemas.projetos import (
    ProjetoCodigoOut,
    ProjetoConviteCreate,
    ProjetoConviteEnviadoOut,
    ProjetoCreate,
    ProjetoMembroOut,
    ProjetoOut,
    ProjetoUpdate,
    VincularObra,
)
from app.schemas.revisoes import (
    ContadorRevisoes,
    RevisaoArquivoOut,
    RevisaoCreate,
    RevisaoDecisao,
    RevisaoOut,
)
from app.schemas.templates import AplicarTemplateIn
from app.services import moodboard as mb_svc
from app.services import orcamentos as orc_svc
from app.services import projeto_vinculo as vinc_svc
from app.services import projetos as proj_svc
from app.services import revisoes as rev_svc

router = APIRouter()


# ============================ projeto ============================
@router.post("", response_model=ProjetoOut, status_code=status.HTTP_201_CREATED)
async def criar_projeto(data: ProjetoCreate, session: DbSession, user_id: CurrentUserId):
    return await proj_svc.create_projeto(session, user_id, data)


@router.get("", response_model=list[ProjetoOut])
async def listar_projetos(session: DbSession):
    return await proj_svc.list_projetos(session)


@router.get("/{projeto_id}", response_model=ProjetoOut)
async def get_projeto(projeto_id: uuid.UUID, session: DbSession):
    return await proj_svc.get_projeto(session, projeto_id)


@router.patch("/{projeto_id}", response_model=ProjetoOut)
async def atualizar_projeto(
    projeto_id: uuid.UUID, data: ProjetoUpdate, session: DbSession, user_id: CurrentUserId
):
    return await proj_svc.update_projeto(session, user_id, projeto_id, data)


@router.post("/{projeto_id}/vincular-obra", response_model=ProjetoOut)
async def vincular_obra(
    projeto_id: uuid.UUID, data: VincularObra, session: DbSession, user_id: CurrentUserId
):
    return await proj_svc.vincular_obra(session, user_id, projeto_id, data.obra_id)


@router.get("/{projeto_id}/audit")
async def listar_audit(projeto_id: uuid.UUID, session: DbSession):
    return await proj_svc.list_audit(session, projeto_id)


# ============================ vínculo ============================
@router.get("/{projeto_id}/membros", response_model=list[ProjetoMembroOut])
async def listar_membros(projeto_id: uuid.UUID, session: DbSession):
    return await vinc_svc.list_membros(session, projeto_id)


@router.delete("/{projeto_id}/membros/{membro_id}")
async def remover_membro(
    projeto_id: uuid.UUID, membro_id: uuid.UUID, session: DbSession, user_id: CurrentUserId
):
    return await vinc_svc.remove_membro(session, user_id, projeto_id, membro_id)


@router.post(
    "/{projeto_id}/convites",
    response_model=ProjetoConviteEnviadoOut,
    status_code=status.HTTP_201_CREATED,
)
async def convidar(
    projeto_id: uuid.UUID, data: ProjetoConviteCreate, session: DbSession, user_id: CurrentUserId
):
    return await vinc_svc.convidar_por_email(session, user_id, projeto_id, data.email)


@router.post(
    "/{projeto_id}/codigo", response_model=ProjetoCodigoOut, status_code=status.HTTP_201_CREATED
)
async def gerar_codigo(projeto_id: uuid.UUID, session: DbSession, user_id: CurrentUserId):
    return await vinc_svc.gerar_codigo(session, user_id, projeto_id)


@router.get("/{projeto_id}/codigo", response_model=ProjetoCodigoOut)
async def get_codigo(projeto_id: uuid.UUID, session: DbSession):
    return await vinc_svc.get_codigo_ativo(session, projeto_id)


@router.delete("/{projeto_id}/codigo")
async def revogar_codigo(projeto_id: uuid.UUID, session: DbSession, user_id: CurrentUserId):
    return await vinc_svc.revogar_codigo(session, user_id, projeto_id)


# ============================ revisões ============================
@router.post(
    "/{projeto_id}/revisoes", response_model=RevisaoOut, status_code=status.HTTP_201_CREATED
)
async def subir_revisao(
    projeto_id: uuid.UUID, data: RevisaoCreate, session: DbSession, user_id: CurrentUserId
):
    return await rev_svc.subir(session, user_id, projeto_id, data)


@router.get("/{projeto_id}/revisoes", response_model=list[RevisaoOut])
async def listar_revisoes(projeto_id: uuid.UUID, session: DbSession):
    return await rev_svc.list_revisoes(session, projeto_id)


# rota estática antes da paramétrica {revisao_id} (uuid não casa "contador")
@router.get("/{projeto_id}/revisoes/contador", response_model=ContadorRevisoes)
async def contador_revisoes(projeto_id: uuid.UUID, session: DbSession):
    return await rev_svc.contador(session, projeto_id)


@router.get("/{projeto_id}/revisoes/{revisao_id}", response_model=RevisaoOut)
async def get_revisao(projeto_id: uuid.UUID, revisao_id: uuid.UUID, session: DbSession):
    return await rev_svc.get_revisao(session, projeto_id, revisao_id)


@router.post("/{projeto_id}/revisoes/{revisao_id}/decisao", response_model=RevisaoOut)
async def decidir_revisao(
    projeto_id: uuid.UUID,
    revisao_id: uuid.UUID,
    data: RevisaoDecisao,
    session: DbSession,
    user_id: CurrentUserId,
):
    return await rev_svc.decidir(session, user_id, projeto_id, revisao_id, data)


@router.get("/{projeto_id}/revisoes/{revisao_id}/arquivos", response_model=list[RevisaoArquivoOut])
async def listar_arquivos(projeto_id: uuid.UUID, revisao_id: uuid.UUID, session: DbSession):
    return await rev_svc.list_arquivos(session, projeto_id, revisao_id)


@router.post(
    "/{projeto_id}/revisoes/{revisao_id}/arquivos",
    response_model=RevisaoArquivoOut,
    status_code=status.HTTP_201_CREATED,
)
async def subir_arquivo(
    projeto_id: uuid.UUID,
    revisao_id: uuid.UUID,
    session: DbSession,
    user_id: CurrentUserId,
    id: Annotated[uuid.UUID, Form()],
    arquivo: Annotated[UploadFile, File()],
):
    return await rev_svc.upload_arquivo(session, user_id, projeto_id, revisao_id, id, arquivo)


@router.get("/{projeto_id}/revisoes/{revisao_id}/arquivos/{arquivo_id}/conteudo")
async def conteudo_arquivo(
    projeto_id: uuid.UUID,
    revisao_id: uuid.UUID,
    arquivo_id: uuid.UUID,
    session: DbSession,
    _user_id: CurrentUserId,
    tipo: Annotated[str, Query(pattern="^(full|thumb)$")] = "full",
):
    data, content_type, nome = await rev_svc.serve_arquivo(
        session, projeto_id, revisao_id, arquivo_id, tipo
    )
    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Cache-Control": "private, max-age=3600",
            "Content-Disposition": f'inline; filename="{nome}"',
        },
    )


@router.delete("/{projeto_id}/revisoes/{revisao_id}/arquivos/{arquivo_id}")
async def remover_arquivo(
    projeto_id: uuid.UUID,
    revisao_id: uuid.UUID,
    arquivo_id: uuid.UUID,
    session: DbSession,
    user_id: CurrentUserId,
):
    return await rev_svc.delete_arquivo(session, user_id, projeto_id, revisao_id, arquivo_id)


# ============================ moodboard ============================
@router.get("/{projeto_id}/moodboard/secoes", response_model=list[SecaoOut])
async def listar_secoes(projeto_id: uuid.UUID, session: DbSession):
    return await mb_svc.list_secoes(session, projeto_id)


@router.post(
    "/{projeto_id}/moodboard/secoes", response_model=SecaoOut, status_code=status.HTTP_201_CREATED
)
async def criar_secao(
    projeto_id: uuid.UUID, data: SecaoCreate, session: DbSession, user_id: CurrentUserId
):
    return await mb_svc.create_secao(session, user_id, projeto_id, data)


@router.patch("/{projeto_id}/moodboard/secoes/{secao_id}", response_model=SecaoOut)
async def atualizar_secao(
    projeto_id: uuid.UUID,
    secao_id: uuid.UUID,
    data: SecaoUpdate,
    session: DbSession,
    user_id: CurrentUserId,
):
    return await mb_svc.update_secao(session, user_id, projeto_id, secao_id, data)


@router.delete("/{projeto_id}/moodboard/secoes/{secao_id}")
async def remover_secao(
    projeto_id: uuid.UUID, secao_id: uuid.UUID, session: DbSession, user_id: CurrentUserId
):
    return await mb_svc.delete_secao(session, user_id, projeto_id, secao_id)


@router.get("/{projeto_id}/moodboard/itens", response_model=list[MoodboardItemOut])
async def listar_itens(projeto_id: uuid.UUID, session: DbSession):
    return await mb_svc.list_itens(session, projeto_id)


@router.post(
    "/{projeto_id}/moodboard/itens",
    response_model=MoodboardItemOut,
    status_code=status.HTTP_201_CREATED,
)
async def subir_item(
    projeto_id: uuid.UUID,
    session: DbSession,
    user_id: CurrentUserId,
    id: Annotated[uuid.UUID, Form()],
    arquivo: Annotated[UploadFile, File()],
    secao_id: Annotated[uuid.UUID | None, Form()] = None,
    legenda: Annotated[str | None, Form()] = None,
):
    return await mb_svc.upload_item(session, user_id, projeto_id, id, secao_id, legenda, arquivo)


@router.get("/{projeto_id}/moodboard/itens/{item_id}/conteudo")
async def conteudo_item(
    projeto_id: uuid.UUID,
    item_id: uuid.UUID,
    session: DbSession,
    _user_id: CurrentUserId,
    tipo: Annotated[str, Query(pattern="^(full|thumb)$")] = "thumb",
):
    data, content_type, nome = await mb_svc.serve_item(session, projeto_id, item_id, tipo)
    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Cache-Control": "private, max-age=3600",
            "Content-Disposition": f'inline; filename="{nome}"',
        },
    )


@router.delete("/{projeto_id}/moodboard/itens/{item_id}")
async def remover_item(
    projeto_id: uuid.UUID, item_id: uuid.UUID, session: DbSession, user_id: CurrentUserId
):
    return await mb_svc.delete_item(session, user_id, projeto_id, item_id)


# ============================ orçamento ============================
@router.get("/{projeto_id}/orcamento/versoes", response_model=list[VersaoResumoOut])
async def listar_orcamento_versoes(projeto_id: uuid.UUID, session: DbSession):
    return await orc_svc.list_versoes(session, projeto_id)


@router.post(
    "/{projeto_id}/orcamento/versoes",
    response_model=OrcamentoVersaoOut,
    status_code=status.HTTP_201_CREATED,
)
async def criar_orcamento_versao(
    projeto_id: uuid.UUID, data: CriarVersaoIn, session: DbSession, user_id: CurrentUserId
):
    return await orc_svc.criar_versao(session, user_id, projeto_id, data.id)


@router.get("/{projeto_id}/orcamento/versoes/{versao_id}", response_model=OrcamentoVersaoOut)
async def get_orcamento_versao(projeto_id: uuid.UUID, versao_id: uuid.UUID, session: DbSession):
    return await orc_svc.get_versao(session, projeto_id, versao_id)


@router.patch("/{projeto_id}/orcamento/versoes/{versao_id}", response_model=OrcamentoVersaoOut)
async def atualizar_orcamento_versao(
    projeto_id: uuid.UUID,
    versao_id: uuid.UUID,
    data: VersaoParams,
    session: DbSession,
    user_id: CurrentUserId,
):
    return await orc_svc.atualizar_params(session, user_id, projeto_id, versao_id, data)


@router.post(
    "/{projeto_id}/orcamento/versoes/{versao_id}/itens",
    response_model=OrcamentoVersaoOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_orcamento_item(
    projeto_id: uuid.UUID,
    versao_id: uuid.UUID,
    data: OrcItemCreate,
    session: DbSession,
    user_id: CurrentUserId,
):
    return await orc_svc.add_item(session, user_id, projeto_id, versao_id, data)


@router.patch(
    "/{projeto_id}/orcamento/versoes/{versao_id}/itens/{item_id}",
    response_model=OrcamentoVersaoOut,
)
async def edit_orcamento_item(
    projeto_id: uuid.UUID,
    versao_id: uuid.UUID,
    item_id: uuid.UUID,
    data: OrcItemUpdate,
    session: DbSession,
    user_id: CurrentUserId,
):
    return await orc_svc.edit_item(session, user_id, projeto_id, versao_id, item_id, data)


@router.delete(
    "/{projeto_id}/orcamento/versoes/{versao_id}/itens/{item_id}",
    response_model=OrcamentoVersaoOut,
)
async def del_orcamento_item(
    projeto_id: uuid.UUID,
    versao_id: uuid.UUID,
    item_id: uuid.UUID,
    session: DbSession,
    user_id: CurrentUserId,
):
    return await orc_svc.delete_item(session, user_id, projeto_id, versao_id, item_id)


@router.post(
    "/{projeto_id}/orcamento/versoes/{versao_id}/importar", response_model=OrcamentoVersaoOut
)
async def importar_orcamento(
    projeto_id: uuid.UUID,
    versao_id: uuid.UUID,
    session: DbSession,
    user_id: CurrentUserId,
    arquivo: Annotated[UploadFile, File()],
):
    return await orc_svc.importar(session, user_id, projeto_id, versao_id, arquivo)


@router.post(
    "/{projeto_id}/orcamento/versoes/{versao_id}/aplicar-template",
    response_model=OrcamentoVersaoOut,
)
async def aplicar_template_orcamento(
    projeto_id: uuid.UUID,
    versao_id: uuid.UUID,
    data: AplicarTemplateIn,
    session: DbSession,
    user_id: CurrentUserId,
):
    return await orc_svc.aplicar_template(
        session, user_id, projeto_id, versao_id, data.template_id, data.ambiente_nome, data.area_m2
    )
