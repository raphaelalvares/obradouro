"""Rotas dos Templates de ambiente (Livro de referências · Fatia 2), prefixo /me/templates.

Biblioteca do arquiteto (nível-conta, RLS self). CRUD de template + itens + 'promover' (salvar
linhas reais como template). 'Aplicar template' fica no orçamento (rota .../aplicar-template)."""

import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentUserId, DbSession
from app.schemas.templates import (
    PromoverTemplateIn,
    TemplateCreate,
    TemplateItemCreate,
    TemplateItemUpdate,
    TemplateOut,
    TemplateResumoOut,
    TemplateUpdate,
)
from app.services import templates as tpl_svc

router = APIRouter()


@router.get("", response_model=list[TemplateResumoOut])
async def listar_templates(session: DbSession):
    return await tpl_svc.listar(session)


@router.post("", response_model=TemplateOut, status_code=status.HTTP_201_CREATED)
async def criar_template(data: TemplateCreate, session: DbSession, user_id: CurrentUserId):
    return await tpl_svc.criar(session, user_id, data)


# rota ESTÁTICA antes da paramétrica
@router.post("/promover", response_model=TemplateOut, status_code=status.HTTP_201_CREATED)
async def promover_template(data: PromoverTemplateIn, session: DbSession, user_id: CurrentUserId):
    return await tpl_svc.promover(session, user_id, data)


@router.get("/{template_id}", response_model=TemplateOut)
async def get_template(template_id: uuid.UUID, session: DbSession):
    return await tpl_svc.get(session, template_id)


@router.patch("/{template_id}", response_model=TemplateOut)
async def atualizar_template(
    template_id: uuid.UUID, data: TemplateUpdate, session: DbSession, user_id: CurrentUserId
):
    return await tpl_svc.atualizar(session, user_id, template_id, data)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def excluir_template(template_id: uuid.UUID, session: DbSession, user_id: CurrentUserId):
    await tpl_svc.excluir(session, user_id, template_id)


@router.post("/{template_id}/itens", response_model=TemplateOut)
async def add_template_item(
    template_id: uuid.UUID, data: TemplateItemCreate, session: DbSession, user_id: CurrentUserId
):
    return await tpl_svc.add_item(session, user_id, template_id, data)


@router.patch("/{template_id}/itens/{item_id}", response_model=TemplateOut)
async def edit_template_item(
    template_id: uuid.UUID,
    item_id: uuid.UUID,
    data: TemplateItemUpdate,
    session: DbSession,
    user_id: CurrentUserId,
):
    return await tpl_svc.edit_item(session, user_id, template_id, item_id, data)


@router.delete("/{template_id}/itens/{item_id}", response_model=TemplateOut)
async def del_template_item(
    template_id: uuid.UUID, item_id: uuid.UUID, session: DbSession, user_id: CurrentUserId
):
    return await tpl_svc.delete_item(session, user_id, template_id, item_id)
