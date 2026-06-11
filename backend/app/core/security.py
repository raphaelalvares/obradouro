"""Validação do JWT do Supabase — local, via JWKS assimétrico (sem chamar o Auth por request).

O JWT só identifica a PESSOA (claim `sub`). Papel e tenant (arquiteto/cliente/prestador) NÃO
vêm do JWT — vivem em `obra_membros` e são resolvidos por RLS + regra de negócio.
"""

from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.core.config import get_settings

# Só algoritmos ASSIMÉTRICOS. NUNCA incluir HS256 junto (evita "algorithm confusion").
ALGORITHMS = ["RS256", "ES256"]


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


_bearer = HTTPBearer(auto_error=True)


def verify_supabase_jwt(
    cred: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
) -> dict:
    """Dependency FastAPI: valida o Bearer token e devolve os claims."""
    settings = get_settings()
    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(cred.credentials)
        return decode_token(
            cred.credentials,
            signing_key.key,
            audience=settings.SUPABASE_JWT_AUDIENCE,
            issuer=settings.supabase_jwt_issuer,
        )
    except jwt.PyJWTError as e:
        # I3: mensagem genérica — não vaza o detalhe interno do PyJWT (ex.: "Signature has expired",
        # "Invalid audience") p/ o cliente. O motivo real fica no traceback do servidor (from e).
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token inválido ou expirado") from e
