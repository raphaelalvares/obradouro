"""Env mínimo para importar a app nos testes sem depender de um .env real."""

import os

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:pwd@localhost:5432/postgres")
os.environ.setdefault("CORS_ORIGINS", "")
