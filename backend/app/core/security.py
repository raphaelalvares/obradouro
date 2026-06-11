"""Validação do JWT do Supabase — local, via JWKS assimétrico (sem chamar o Auth por request).

O JWT só identifica a PESSOA (claim `sub`). Papel e tenant (arquiteto/cliente/prestador) NÃO
vêm do JWT — vivem em `obra_membros` e são resolvidos por RLS + regra de negócio.
"""

from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.core.config import get_settings

# Só algoritmos ASSIMÉTRICOS. NUNCA incluir HS256 junto (evita "algorithm confusion").
ALGORITHMS = ["RS256", "ES256"]

# B6 (BFF / httpOnly): nome do cookie do access token. O backend (login/callback — inc. 2) o grava
# httpOnly+Secure+SameSite e a API o lê aqui. O header Authorization: Bearer segue aceito DURANTE a
# migração do front (inc. 3); o fallback é removido no inc. 4.
ACCESS_COOKIE = "cria_access"


def decode_token(token: str, key, *, audience: str, issuer: str) -> dict:
    """Decodifica e valida assinatura, exp, aud e iss. Levanta jwt.PyJWTError se inválido."""
    return jwt.decode(
        token,
        key,
        algorithms=ALGORITHMS,
        audience=audience,
        issuer=issuer,
        options={"require": ["exp", "sub", "aud", "iss"]},
    )


@lru_cache
def _jwks_client() -> PyJWKClient:
    # Cacheia o JWK Set (~300s) e refaz fetch se o kid não estiver no cache (cobre rotação).
    return PyJWKClient(get_settings().supabase_jwks_url)


# auto_error=False: sem header NÃO dispara 401 sozinho — o cookie httpOnly pode suprir o token.
_bearer = HTTPBearer(auto_error=False)


def _extract_token(request: Request, cred: HTTPAuthorizationCredentials | None) -> str | None:
    """Token do cookie httpOnly (alvo do B6) ou do header Authorization: Bearer (legado/migração).
    Cookie tem precedência: é o estado-final; o Bearer some quando o front migrar (inc. 3/4)."""
    return request.cookies.get(ACCESS_COOKIE) or (cred.credentials if cred else None)


def verify_supabase_jwt(
    request: Request,
    cred: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> dict:
    """Dependency FastAPI: valida o JWT (cookie httpOnly OU Bearer) e devolve os claims."""
    token = _extract_token(request, cred)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "não autenticado")
    settings = get_settings()
    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(token)
        return decode_token(
            token,
            signing_key.key,
            audience=settings.SUPABASE_JWT_AUDIENCE,
            issuer=settings.supabase_jwt_issuer,
        )
    except jwt.PyJWTError as e:
        # I3: mensagem genérica — não vaza o detalhe interno do PyJWT (ex.: "Signature has expired",
        # "Invalid audience") p/ o cliente. O motivo real fica no traceback do servidor (from e).
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token inválido ou expirado") from e
