"""Testes da validação de JWT (decode_token) — sem rede: gera par RSA local e assina/valida."""

import datetime as dt

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.security import decode_token

ISSUER = "https://example.supabase.co/auth/v1"
AUDIENCE = "authenticated"
SUB = "11111111-1111-1111-1111-111111111111"


def _keypair() -> tuple[bytes, bytes]:
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = priv.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    pub_pem = priv.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return priv_pem, pub_pem


def _token(priv_pem: bytes, **overrides) -> str:
    now = dt.datetime.now(dt.UTC)
    payload = {
        "sub": SUB,
        "aud": AUDIENCE,
        "iss": ISSUER,
        "iat": now,
        "exp": now + dt.timedelta(hours=1),
    }
    payload.update(overrides)
    return jwt.encode(payload, priv_pem, algorithm="RS256")


def test_valid_token():
    priv, pub = _keypair()
    claims = decode_token(_token(priv), pub, audience=AUDIENCE, issuer=ISSUER)
    assert claims["sub"] == SUB


def test_wrong_issuer_rejected():
    priv, pub = _keypair()
    with pytest.raises(jwt.PyJWTError):
        decode_token(_token(priv), pub, audience=AUDIENCE, issuer="https://evil/auth/v1")


def test_wrong_audience_rejected():
    priv, pub = _keypair()
    with pytest.raises(jwt.PyJWTError):
        decode_token(_token(priv, aud="anon"), pub, audience=AUDIENCE, issuer=ISSUER)


def test_expired_token_rejected():
    priv, pub = _keypair()
    past = dt.datetime.now(dt.UTC) - dt.timedelta(hours=2)
    with pytest.raises(jwt.PyJWTError):
        decode_token(_token(priv, iat=past, exp=past), pub, audience=AUDIENCE, issuer=ISSUER)


def test_wrong_key_rejected():
    priv, _ = _keypair()
    _, other_pub = _keypair()
    with pytest.raises(jwt.PyJWTError):
        decode_token(_token(priv), other_pub, audience=AUDIENCE, issuer=ISSUER)
