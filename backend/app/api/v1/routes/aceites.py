"""Aceite de documentos legais do usuário corrente (Termos/Privacidade) — prova versionada."""

from fastapi import APIRouter

from app.api.deps import Claims, DbSession
from app.schemas.aceite import AceiteOut, AceiteRegistrarIn, DocumentoVersaoOut
from app.services import aceites as aceites_svc
from app.services import me as me_svc

router = APIRouter()


@router.get("/aceites", response_model=list[AceiteOut])
async def listar_aceites(session: DbSession):
    return await aceites_svc.listar(session)


@router.get("/aceites/pendentes", response_model=list[DocumentoVersaoOut])
async def aceites_pendentes(session: DbSession, claims: Claims):
    """Documentos que faltam aceitar na versão vigente. Auto-carimba quando o aceite foi atestado
    no metadata do signup (e-mail/senha) — assim independe do dispositivo onde a sessão nasce."""
    await me_svc.get_or_create_me(session, claims.get("email"))
    meta = claims.get("user_metadata") or {}
    if meta.get("aceite"):
        await aceites_svc.registrar(session, "cadastro")
    return await aceites_svc.pendentes(session)


@router.post("/aceites", response_model=list[AceiteOut])
async def registrar_aceites(data: AceiteRegistrarIn, session: DbSession, claims: Claims):
    # garante a profile antes do FK (rede de segurança além do trigger handle_new_user)
    await me_svc.get_or_create_me(session, claims.get("email"))
    return await aceites_svc.registrar(session, data.origem)
