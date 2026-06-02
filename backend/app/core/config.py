"""Configuração da aplicação, lida de variáveis de ambiente / .env."""

from functools import lru_cache
from typing import Annotated

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Aplicação
    ENVIRONMENT: str = "development"
    PROJECT_NAME: str = "CRIA API"
    VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"

    # Supabase
    SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: SecretStr  # admin — só no backend, nunca nos apps
    SUPABASE_ANON_KEY: SecretStr | None = None

    # Postgres (driver asyncpg): postgresql+asyncpg://user:pass@host:5432/postgres
    DATABASE_URL: SecretStr

    # JWT do Supabase (validação local via JWKS assimétrico)
    SUPABASE_JWT_AUDIENCE: str = "authenticated"

    # CORS: lista (aceita string separada por vírgula no .env).
    # NoDecode evita que o pydantic-settings tente fazer json.loads do valor
    # do env antes do validator abaixo (a string "a,b" não é JSON válido).
    CORS_ORIGINS: Annotated[list[str], NoDecode] = []

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_cors(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def supabase_jwt_issuer(self) -> str:
        return f"{self.SUPABASE_URL.rstrip('/')}/auth/v1"

    @property
    def supabase_jwks_url(self) -> str:
        return f"{self.supabase_jwt_issuer}/.well-known/jwks.json"


@lru_cache
def get_settings() -> Settings:
    """Settings em cache (lido uma vez por processo)."""
    return Settings()
