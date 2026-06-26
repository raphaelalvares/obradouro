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

    # URL base do front (web do arquiteto) — usada nos redirects do Stripe Checkout/Portal.
    # None = cai na 1ª origem de CORS, senão localhost de dev.
    APP_BASE_URL: str | None = None

    # URL pública da API (ex.: https://api.obradouro.com.br) — base do redirect_to do OAuth (B6 2c).
    # O callback precisa estar nos Redirect URLs do Supabase (Authentication > URL Configuration).
    API_BASE_URL: str | None = None

    # Cobrança (Fase 9 — Stripe). TODAS opcionais: sem elas o módulo degrada (app segue normal,
    # endpoints de cobrança respondem "não configurada"). Chaves só no backend, nunca nos apps.
    STRIPE_SECRET_KEY: SecretStr | None = None
    STRIPE_WEBHOOK_SECRET: SecretStr | None = None  # verifica a assinatura do webhook
    STRIPE_PRICE_PRO: str | None = None  # Price ID (recorrente) do plano Pro no Stripe

    # E-mail transacional (Resend, via API HTTP). Opcionais: sem elas o envio é NO-OP (só loga) —
    # nunca quebra o fluxo. Chaves só no backend. RESEND_FROM = remetente verificado no Resend
    # (ex.: "CRIA <proposta@obradouro.com.br>").
    RESEND_API_KEY: SecretStr | None = None
    RESEND_FROM: str | None = None

    # LLM local (Ollama) — humaniza os LEMBRETES comerciais. Opcional e nasce OFF: o módulo de
    # lembretes funciona 100% sem LLM (usa a mensagem-base de cada regra). Com a flag ON, o backend
    # chama o Ollama (on-prem) só pra reescrever cada lembrete; se off/lento/erro, cai na baseline
    # (nunca quebra o GET). O dado (nome/contato) não sai da máquina — um LLM remoto exigiria
    # revisão de privacidade/LGPD; por isso o default é o Ollama local.
    LEMBRETES_LLM_ENABLED: bool = False
    OLLAMA_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:3b"
    OLLAMA_TIMEOUT_S: float = 4.0
    LEMBRETES_LLM_MAX_ITENS: int = 8  # cap de itens humanizados por request (latência do 3B)

    # Limiares das regras de lembrete (globais; tunáveis por env SEM migration — não são por-tenant
    # ainda). TZ p/ comparar datas: o servidor pode estar em UTC e o arquiteto em America/Sao_Paulo.
    LEMBRETES_TZ: str = "America/Sao_Paulo"
    LEMBRETES_DIAS_ESFRIANDO: int = 14
    LEMBRETES_DIAS_PROPOSTA: int = 7
    LEMBRETES_DIAS_LEAD_NOVO: int = 3
    LEMBRETES_DIAS_GANHO: int = 3
    LEMBRETES_VALOR_ALTO: float = 50000

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
    # Teto de operações CPU-bound simultâneas (imagem/PDF/xlsx/zip) — ver app.core.concurrency.
    # O backend roda 1 worker (1 event loop); cada operação dessas carrega o arquivo inteiro +
    # buffers de pixel na RAM. Com 1 vCPU / 4GB o default é 2 (não adianta mais que ~nº de vCPU,
    # e RAM é o limite real). Tunável por env SEM rebuild.
    HEAVY_OPS_CONCURRENCY: int = 2

    # Auth BFF (B6): atributos dos cookies de sessão (access/refresh/csrf). Em produção front e API
    # são cross-site (Vercel ↔ api.obradouro.com.br) → SameSite=None;Secure. Em DEV local (http) use
    # AUTH_COOKIE_SAMESITE=lax e AUTH_COOKIE_SECURE=false (o browser rejeita None sem HTTPS).
    AUTH_COOKIE_SECURE: bool = True
    AUTH_COOKIE_SAMESITE: str = "none"
    AUTH_COOKIE_DOMAIN: str | None = None  # None = host-only (escopo do host da API)
    # Janela de INATIVIDADE da sessão (s). Os cookies de longa duração (refresh + csrf) são
    # DESLIZANTES: cada /login e /refresh os re-arma com esta validade. Passado este tempo SEM
    # nenhuma renovação (usuário inativo, ou de fato fora do app), o browser descarta os cookies →
    # o /refresh fica sem credencial → 401 → o usuário cai no login. Evita a sessão "eterna" pós
    # 1º login (antes o refresh vivia 30 dias deslizantes ≈ pra sempre). Default 6h. Tunável p/ env.
    # Isto é o corte do LADO BROWSER; o /refresh também enforça no SERVIDOR via cookie cria_seen
    # (ver auth_cookies). Opcional/extra: alinhar o "Inactivity timeout" das Sessions do Supabase.
    AUTH_IDLE_TIMEOUT_SECONDS: int = 6 * 60 * 60
    # Segredo p/ assinar (HMAC) o cookie cria_seen — o carimbo de "última atividade" que o /refresh
    # checa p/ enforçar a inatividade no servidor (não confiar só no max-age do browser). Opcional:
    # vazio → deriva da SERVICE_ROLE_KEY (sempre presente). Trocá-lo desloga todos (re-login).
    AUTH_SESSION_SECRET: SecretStr | None = None

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
    def cobranca_configurada(self) -> bool:
        """Stripe utilizável? (chave secreta + price do Pro). Sem isso o módulo degrada."""
        return bool(self.STRIPE_SECRET_KEY and self.STRIPE_PRICE_PRO)

    @property
    def email_configurado(self) -> bool:
        """Resend utilizável? (API key + remetente). Sem isso o envio é no-op (só loga)."""
        return bool(self.RESEND_API_KEY and self.RESEND_FROM)

    @property
    def lembretes_llm_ativo(self) -> bool:
        """Humanizador do 3B ligado? Sem isso os lembretes usam a mensagem-base das regras."""
        return self.LEMBRETES_LLM_ENABLED

    @property
    def app_base_url(self) -> str:
        """Origem do front p/ os redirects do Stripe (success/cancel/return)."""
        if self.APP_BASE_URL:
            return self.APP_BASE_URL.rstrip("/")
        if self.CORS_ORIGINS:
            return self.CORS_ORIGINS[0].rstrip("/")
        return "http://localhost:5173"

    @property
    def auth_refresh_cookie_path(self) -> str:
        """Path do cookie de refresh: só vai aos endpoints /auth (não no resto da API)."""
        return f"{self.API_V1_PREFIX}/auth"

    @property
    def auth_session_secret(self) -> bytes:
        """Chave HMAC do cookie cria_seen. Usa AUTH_SESSION_SECRET se setado; senão deriva da
        SERVICE_ROLE_KEY (sempre presente) — assim não exige um env novo p/ a trava funcionar."""
        raw = (
            self.AUTH_SESSION_SECRET.get_secret_value()
            if self.AUTH_SESSION_SECRET
            else self.SUPABASE_SERVICE_ROLE_KEY.get_secret_value()
        )
        return raw.encode("utf-8")

    @property
    def api_base_url(self) -> str:
        """URL pública da API (sem barra final). Vazio = OAuth não configurado."""
        return (self.API_BASE_URL or "").rstrip("/")

    @property
    def oauth_callback_url(self) -> str:
        return f"{self.api_base_url}{self.API_V1_PREFIX}/auth/callback"

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
