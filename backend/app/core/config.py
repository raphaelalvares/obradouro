"""Configuração da aplicação, lida de variáveis de ambiente / .env."""

import re
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
    PROJECT_NAME: str = "Obra D'Ouro API"
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
    # Versão da API do Stripe (ex.: "2025-08-27.basil"). None = default da lib. Pine p/ casar a
    # serialização do endpoint de webhook e dos retrieve — determinístico entre lib e conta.
    STRIPE_API_VERSION: str | None = None
    # Cupom/promotion code de WIN-BACK aplicado no re-checkout de quem caiu p/ free (jornada de
    # re-sell). É o ID de um "promotion code" do Stripe (promo_...). None = win-back sem desconto.
    STRIPE_PROMO_WINBACK: str | None = None
    # Add-on de ARMAZENAMENTO: Price recorrente POR GB (unit_amount = preço/GB abaixo, quantity = nº
    # de GB; mensal como os planos). Sem ele, contratar storage responde 503.
    STRIPE_PRICE_ARMAZENAMENTO: str | None = None
    # Preço/GB (centavos) SÓ p/ EXIBIR na UI — o cobrado sai do Stripe. Deve casar com o Price acima
    # (fonte única no back; o front lê via /me/financeiro e /admin/armazenamento).
    ARMAZENAMENTO_PRECO_GB_CENTAVOS: int = 15
    # Up-sell de storage: % do limite a partir do qual o front mostra o nudge "quase cheio" e o
    # backend (on-write) dispara o e-mail de "contrate mais espaço". Reaviso a cada N dias enquanto
    # seguir cheio (o dedupe periódico evita spam). Ver notificacoes + planos.get_quota.
    ARMAZENAMENTO_AVISO_PCT: int = 90
    ARMAZENAMENTO_REAVISO_DIAS: int = 7

    # E-mail transacional (Resend, via API HTTP). Opcionais: sem elas o envio é NO-OP (só loga) —
    # nunca quebra o fluxo. Chaves só no backend. RESEND_FROM = remetente verificado no Resend
    # (ex.: "Obra D'Ouro <proposta@obradouro.com.br>").
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

    # Assistente conversacional (chat). PRECISA do Ollama ligado (o card de lembretes funciona sem,
    # este não). Nasce OFF. Reusa OLLAMA_URL/OLLAMA_MODEL; usa timeout maior (geração de texto).
    ASSISTENTE_ENABLED: bool = False
    OLLAMA_CHAT_TIMEOUT_S: float = 30.0
    ASSISTENTE_MAX_OPORTUNIDADES: int = 30  # cap do snapshot enviado ao 3B (limita o contexto)
    ASSISTENTE_MAX_HISTORICO: int = 6  # últimas N mensagens da conversa enviadas ao modelo

    # Autenticação do Ollama REMOTO (quando exposto por túnel, ex.: Cloudflare Tunnel + Access). Sem
    # isso (Ollama local) nenhum header é enviado. Service Token do Cloudflare Access (recomendado):
    OLLAMA_CF_ACCESS_CLIENT_ID: str | None = None
    OLLAMA_CF_ACCESS_CLIENT_SECRET: SecretStr | None = None
    # Alternativa: bearer simples (se houver um proxy com auth na frente do Ollama).
    OLLAMA_BEARER_TOKEN: SecretStr | None = None

    # CORS: lista de origens EXATAS (aceita string separada por vírgula no .env).
    # NoDecode evita que o pydantic-settings tente fazer json.loads do valor
    # do env antes do validator abaixo (a string "a,b" não é JSON válido).
    CORS_ORIGINS: Annotated[list[str], NoDecode] = []
    # Regex opcional p/ origens dinâmicas (ex.: previews da Vercel). DEVE ser ancorado (^...$) — um
    # regex sem âncora casa domínios do atacante. E fixe o slug do time (…-<slug>.vercel.app), senão
    # QUALQUER projeto obradouro-*.vercel.app de terceiros casa (namespace público/squattável).
    # Validado no _anchor_cors_regex. Evite em ambiente com cookie. Casado via allow_origin_regex.
    CORS_ORIGIN_REGEX: str | None = None

    # Storage (Fase 4) — backend de BYTES atrás do módulo app.services.storage (interface trocável).
    # 'local' = disco (DEV, sem credencial); 'drive' = Google Drive (OAuth do dono); 'supabase'/'s3'
    # = slots futuros (mesma interface).
    STORAGE_BACKEND: str = "local"
    # Raiz do adapter 'local' (relativa ao CWD do backend, ou absoluta). Fora do git.
    STORAGE_DIR: str = ".storage"
    # Storage 'drive' (Google Drive via OAuth da conta do dono — ver services/storage/drive.py e
    # scripts/mint_drive_token.py). Só usados quando STORAGE_BACKEND='drive'. CLIENT_SECRET e
    # REFRESH_TOKEN são SEGREDOS (nunca no front). A pasta-raiz é criada pela própria app (escopo
    # drive.file) e seu id vai em ROOT_FOLDER_ID (o script imprime os quatro valores).
    GOOGLE_DRIVE_CLIENT_ID: str | None = None
    GOOGLE_DRIVE_CLIENT_SECRET: SecretStr | None = None
    GOOGLE_DRIVE_REFRESH_TOKEN: SecretStr | None = None
    GOOGLE_DRIVE_ROOT_FOLDER_ID: str | None = None
    # Teto físico do POOL de storage (MB) que o painel admin usa como total ao alocar espaço. None =
    # usa o que o backend reporta da conta (Drive: about.storageQuota.limit — os 5 TB reais). Sirva
    # um valor menor pra RESERVAR folga p/ Gmail/Fotos/lixeira (ex.: 4_800_000 = 4,8 TB).
    STORAGE_POOL_MB: int | None = None
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

    # Export DURÁVEL (Fase 8 — reaper). O worker do export roda in-process (FastAPI BackgroundTasks,
    # 1 worker uvicorn); se o processo reinicia/deploya/cai, o job fica órfão em 'pendente'/
    # 'processando'. O reaper (loop no lifespan) varre e re-dispara. Tunável por env SEM rebuild.
    EXPORT_REAPER_ENABLED: bool = True
    EXPORT_REAPER_INTERVAL_SECONDS: int = 300  # cadência do loop (5 min); 1º sweep é no boot
    EXPORT_PENDENTE_GRACE_SECONDS: int = 60  # 'pendente' órfão além disso → re-dispara
    EXPORT_PROCESSANDO_LEASE_SECONDS: int = 1200  # 'processando' vivo além disso → worker morreu
    EXPORT_MAX_TENTATIVAS: int = 3  # após N pegadas sem sucesso o job vira 'erro' (anti job-veneno)
    EXPORT_REAPER_BATCH: int = 20  # teto de jobs por varredura (evita thundering-herd/OOM)

    # Reaper de COBRANÇA (jornada de win-back). Loop no lifespan que varre quem caiu p/ free e ainda
    # não foi tocado no estágio D+1/D+7/D+30, e manda o e-mail de volta (dedupe por estágio). Só
    # tempo (não depende de evento Stripe). Cadência folgada (horária basta p/ win-back). Sem Resend
    # configurado o tick vira no-op. WINBACK_MAX_DIAS limita a janela varrida.
    COBRANCA_REAPER_ENABLED: bool = True
    COBRANCA_REAPER_INTERVAL_SECONDS: int = 3600  # 1h; 1º sweep no boot
    COBRANCA_WINBACK_MAX_DIAS: int = 30  # não varre quem caiu há mais que isso
    COBRANCA_WINBACK_BATCH: int = 200  # teto de candidatos por varredura
    # Aviso opcional de RENOVAÇÃO próxima (invoice.upcoming). Mensal costuma ser ruído → nasce OFF;
    # ligue p/ mandar "sua assinatura renova em DD/MM por R$X" antes de cada cobrança.
    COBRANCA_AVISO_RENOVACAO: bool = False

    # Rate limiting (defesa-em-profundidade) dos endpoints de bootstrap de credencial (login/signup)
    # In-memory por processo (1 worker uvicorn) — ver app.core.ratelimit. A 1ª linha é o edge
    # (Traefik — docs/infra-edge-hardening.md) + os limites do GoTrue (recebe o IP real do cliente).
    # Tetos conservadores p/ não travar uso legítimo; ENABLED=false desliga (ex.: teste de carga).
    AUTH_RATE_LIMIT_ENABLED: bool = True
    AUTH_RATE_LIMIT_WINDOW_SECONDS: int = 300  # janela de 5 min
    # IP_MAX é GENEROSO de propósito: um escritório atrás de 1 NAT (vários usuários, vários devices)
    # colapsa no mesmo IP → um teto baixo travaria colegas legítimos (429). A defesa fina de brute
    # force é o EMAIL_MAX (por conta) + edge/GoTrue; o IP_MAX só barra flood grosseiro de 1 IP.
    AUTH_RATE_LIMIT_IP_MAX: int = 200  # login+signup por IP na janela (só anti-flood grosseiro)
    AUTH_RATE_LIMIT_EMAIL_MAX: int = 8  # tentativas de login por email na janela (anti brute force)

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
            v = [o.strip() for o in v.split(",") if o.strip()]
        # fail-closed: a API usa allow_credentials=True; '*' + credenciais é inseguro (e o browser
        # rejeita). Recusa o footgun no boot em vez de servir uma config perigosa.
        if isinstance(v, list) and any(o == "*" for o in v):
            raise ValueError(
                "CORS_ORIGINS não pode ser '*' (a API usa credenciais). Liste as origens EXATAS."
            )
        return v

    @field_validator("CORS_ORIGIN_REGEX")
    @classmethod
    def _anchor_cors_regex(cls, v: str | None) -> str | None:
        # um regex sem âncora casa domínios do atacante; exige ^...$. O slug do time
        # (…-<slug>.vercel.app) é responsabilidade do operador (ver docs/environments.md).
        if v:
            if not (v.startswith("^") and v.endswith("$")):
                raise ValueError("CORS_ORIGIN_REGEX deve ser ancorado (^...$).")
            try:  # fail-fast no boot em vez de estourar no 1º preflight (Starlette usa fullmatch)
                re.compile(v)
            except re.error as e:
                raise ValueError(f"CORS_ORIGIN_REGEX inválido: {e}") from e
        return v

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def cobranca_configurada(self) -> bool:
        """Stripe utilizável? (chave secreta + price do Pro). Sem isso o módulo degrada."""
        return bool(self.STRIPE_SECRET_KEY and self.STRIPE_PRICE_PRO)

    @property
    def armazenamento_configurado(self) -> bool:
        """Add-on de storage contratável? (Stripe ok + price por-GB). Sem ele o contratar dá 503."""
        return self.cobranca_configurada and bool(self.STRIPE_PRICE_ARMAZENAMENTO)

    @property
    def email_configurado(self) -> bool:
        """Resend utilizável? (API key + remetente). Sem isso o envio é no-op (só loga)."""
        return bool(self.RESEND_API_KEY and self.RESEND_FROM)

    @property
    def lembretes_llm_ativo(self) -> bool:
        """Humanizador do 3B ligado? Sem isso os lembretes usam a mensagem-base das regras."""
        return self.LEMBRETES_LLM_ENABLED

    @property
    def assistente_ativo(self) -> bool:
        """Chat conversacional ligado? (precisa do Ollama). Sem isso o endpoint degrada."""
        return self.ASSISTENTE_ENABLED

    @property
    def ollama_auth_headers(self) -> dict[str, str]:
        """Headers de auth p/ um Ollama remoto (túnel). Vazio quando o Ollama é local."""
        h: dict[str, str] = {}
        if self.OLLAMA_CF_ACCESS_CLIENT_ID and self.OLLAMA_CF_ACCESS_CLIENT_SECRET:
            h["CF-Access-Client-Id"] = self.OLLAMA_CF_ACCESS_CLIENT_ID
            h["CF-Access-Client-Secret"] = self.OLLAMA_CF_ACCESS_CLIENT_SECRET.get_secret_value()
        if self.OLLAMA_BEARER_TOKEN:
            h["Authorization"] = f"Bearer {self.OLLAMA_BEARER_TOKEN.get_secret_value()}"
        return h

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
