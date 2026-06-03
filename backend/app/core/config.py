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
    # Log de SQL (echo do SQLAlchemy). Explícito p/ não vazar params sensíveis por inércia
    # de ENVIRONMENT — só liga quando você pede (SQL_ECHO=true no .env local).
    SQL_ECHO: bool = False
    PROJECT_NAME: str = "CRIA API"
    VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"

    # Supabase
    SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: SecretStr  # admin — só no backend, nunca nos apps
    SUPABASE_ANON_KEY: SecretStr | None = None

    # Postgres (driver asyncpg): postgresql+asyncpg://user:pass@host:5432/postgres
    DATABASE_URL: SecretStr
    # SSL do DB: produção verifica (padrão). DEV =true relaxa a verificação (o pooler do Supabase
    # usa CA própria; sem o cert da CA o verify falha no Windows). NUNCA usar em produção.
    DB_SSL_INSECURE: bool = False
    # Caminho p/ a CA raiz do Supabase. Setado (e DB_SSL_INSECURE=false) => TLS verify-full contra
    # essa CA (cadeia + hostname). Necessário em produção: o pooler usa CA própria, fora do trust
    # store do SO. Ex.: /app/certs/supabase-ca.crt (cert PÚBLICO, baixado do Dashboard do Supabase).
    DB_SSL_ROOT_CERT: str | None = None

    # JWT do Supabase (validação local via JWKS assimétrico)
    SUPABASE_JWT_AUDIENCE: str = "authenticated"

    # Para onde o link de convite/definir-senha redireciona (deep link mobile ou URL web).
    # None = generate_link sem redirect (cai no Site URL do Supabase).
    INVITE_REDIRECT_URL: str | None = None

    # CORS: lista de origens EXATAS (aceita string separada por vírgula no .env).
    # NoDecode evita que o pydantic-settings tente fazer json.loads do valor
    # do env antes do validator abaixo (a string "a,b" não é JSON válido).
    CORS_ORIGINS: Annotated[list[str], NoDecode] = []
    # Regex opcional p/ origens dinâmicas (ex.: previews da Vercel
    # https://obradouro-*.vercel.app). Casado via allow_origin_regex do CORSMiddleware.
    CORS_ORIGIN_REGEX: str | None = None

    # Storage (Fase 4) — backend de BYTES atrás do módulo app.services.storage (interface trocável).
    # 'local' = disco (DEV, sem credencial); 'drive'/'supabase' = slots futuros (mesma interface).
    STORAGE_BACKEND: str = "local"
    # Raiz do adapter 'local' (relativa ao CWD do backend, ou absoluta). Fora do git.
    STORAGE_DIR: str = ".storage"
    # Limite por upload (MB): acima disso → 413 antes de processar (não estoura memória nem quota).
    MAX_UPLOAD_MB: int = 25
    # Lado maior da miniatura e do 'full' (px); acima do FULL_MAX_PX o 'full' encolhe.
    THUMB_MAX_PX: int = 512
    FULL_MAX_PX: int = 2560

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
