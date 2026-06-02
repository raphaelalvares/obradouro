"""Cliente Supabase Admin (Auth) — usado a partir da Fase 1.

Separado do acesso a dados (que vai por SQLAlchemy/asyncpg em ``app.core.database``).
Este client serve só para operações **administrativas de Auth**: criar usuário
(``auth.admin.create_user``) e gerar links de convite / definição de senha
(``auth.admin.generate_link``).

Recomendação verificada (``docs/infra-notes.md``): em FastAPI async, usar o client
**assíncrono** (``acreate_client``) — o ``create_client`` síncrono bloqueia o event loop.
Na Fase 1 o client é criado uma vez no ``lifespan`` da app e reutilizado.

AVISO: a service/secret key ignora RLS e cria contas. Vive só no backend, nunca nos apps.
"""

from supabase import AsyncClient, AsyncClientOptions, acreate_client

from app.core.config import get_settings


async def create_supabase_admin() -> AsyncClient:
    """Cria o client admin async (service/secret key, sem sessão de usuário)."""
    settings = get_settings()
    return await acreate_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_SERVICE_ROLE_KEY.get_secret_value(),
        options=AsyncClientOptions(auto_refresh_token=False, persist_session=False),
    )
