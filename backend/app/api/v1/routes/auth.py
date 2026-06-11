"""Rotas de auth do BFF (B6 Inc.2a): login / refresh / logout / session com cookies httpOnly + CSRF.

O front não guarda mais o JWT em JS: vai em cookie httpOnly e a API o lê (app.core.security).
A resposta devolve o token CSRF no CORPO — o front guarda em memória e o reenvia no header
X-CSRF-Token (validado pelo CsrfMiddleware). Signup e OAuth (Google/Apple) entram no 2b/2c.
"""

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr

from app.api.deps import Claims
from app.core import auth_cookies
from app.core.config import get_settings
from app.core.security import ACCESS_COOKIE
from app.services import auth as svc

router = APIRouter()

_OAUTH_COOKIE = "cria_oauth"  # guarda o code_verifier do PKCE entre o /oauth e o /callback


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class SignupIn(BaseModel):
    email: EmailStr
    password: str
    nome: str
    telefone: str | None = None
    aceite: bool  # gate server-side: recusa cadastro sem aceite (espelha o checkbox do front)


class SessionOut(BaseModel):
    user_id: str
    csrf: str | None = None  # token CSRF p/ o front guardar em memória e reenviar no header


class SignupOut(BaseModel):
    user_id: str | None = None
    precisa_confirmar_email: bool
    csrf: str | None = None


def _apply(response: Response, sess: dict) -> str:
    return auth_cookies.set_session(
        response,
        access=sess["access_token"],
        refresh=sess["refresh_token"],
        expires_in=int(sess.get("expires_in", 3600)),
    )


@router.post("/login", response_model=SessionOut)
async def login(data: LoginIn, response: Response):
    sess = await svc.login(data.email, data.password)
    csrf = _apply(response, sess)
    return SessionOut(user_id=sess["user"]["id"], csrf=csrf)


@router.post("/signup", response_model=SignupOut)
async def signup(data: SignupIn, response: Response):
    if not data.aceite:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "é necessário aceitar os termos")
    sess = await svc.signup(data.email, data.password, nome=data.nome, telefone=data.telefone)
    user_id, tem_sessao = svc.session_or_pending(sess)
    if tem_sessao:  # autoconfirm: já loga (grava cookies)
        csrf = _apply(response, sess)
        return SignupOut(user_id=user_id, precisa_confirmar_email=False, csrf=csrf)
    # confirmação de email ligada: conta criada, mas sem sessão até confirmar
    return SignupOut(user_id=user_id, precisa_confirmar_email=True)


@router.post("/refresh", response_model=SessionOut)
async def refresh(request: Request, response: Response):
    token = request.cookies.get(auth_cookies.REFRESH_COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "sem sessão")
    sess = await svc.refresh(token)
    csrf = _apply(response, sess)
    return SessionOut(user_id=sess["user"]["id"], csrf=csrf)


@router.post("/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get(ACCESS_COOKIE)
    if token:
        await svc.logout(token)
    auth_cookies.clear_session(response)
    return {"ok": True}


@router.get("/session", response_model=SessionOut)
async def session(request: Request, claims: Claims):
    """Autenticado (cookie/Bearer) → id + token CSRF atual (front re-hidrata após reload)."""
    return SessionOut(user_id=claims["sub"], csrf=request.cookies.get(auth_cookies.CSRF_COOKIE))


# ---------------------------------------------------------------- OAuth (2c, BFF + PKCE)
@router.get("/oauth/{provider}")
async def oauth_start(provider: str):
    """Início do OAuth: gera PKCE, guarda o verifier num cookie e manda o browser ao GoTrue."""
    if provider not in svc.OAUTH_PROVIDERS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "provedor não suportado")
    s = get_settings()
    verifier, challenge = svc.gen_pkce()
    redirect = RedirectResponse(svc.oauth_authorize_url(provider, challenge), status_code=302)
    redirect.set_cookie(  # httpOnly, Lax (sobrevive ao retorno top-level GET), curto
        _OAUTH_COOKIE,
        verifier,
        max_age=600,
        httponly=True,
        secure=s.AUTH_COOKIE_SECURE,
        samesite="lax",
        path=s.auth_refresh_cookie_path,
    )
    return redirect


@router.get("/callback")
async def oauth_callback(request: Request, code: str | None = None):
    """Retorno do provedor: troca o code (+ verifier do cookie) por sessão, grava cookies e manda o
    browser de volta ao front. Em erro, redireciona ao front com ?error=oauth (sem vazar)."""
    s = get_settings()
    front = s.app_base_url
    verifier = request.cookies.get(_OAUTH_COOKIE)
    if not code or not verifier:
        return RedirectResponse(f"{front}/auth/callback?error=oauth", status_code=302)
    try:
        sess = await svc.exchange_pkce(code, verifier)
    except HTTPException:
        return RedirectResponse(f"{front}/auth/callback?error=oauth", status_code=302)
    redirect = RedirectResponse(f"{front}/auth/callback", status_code=302)
    _apply(redirect, sess)  # grava os cookies de sessão na própria resposta de redirect
    redirect.delete_cookie(
        _OAUTH_COOKIE, path=s.auth_refresh_cookie_path, secure=s.AUTH_COOKIE_SECURE, samesite="lax"
    )
    return redirect
