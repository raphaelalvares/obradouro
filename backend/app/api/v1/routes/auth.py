"""Rotas de auth do BFF (B6 Inc.2a): login / refresh / logout / session com cookies httpOnly + CSRF.

O front não guarda mais o JWT em JS: vai em cookie httpOnly e a API o lê (app.core.security).
A resposta devolve o token CSRF no CORPO — o front guarda em memória e o reenvia no header
X-CSRF-Token (validado pelo CsrfMiddleware). Signup e OAuth (Google/Apple) entram no 2b/2c.
"""

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr

from app.api.deps import Claims
from app.core import auth_cookies
from app.core.security import ACCESS_COOKIE
from app.services import auth as svc

router = APIRouter()


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class SessionOut(BaseModel):
    user_id: str
    csrf: str | None = None  # token CSRF p/ o front guardar em memória e reenviar no header


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
