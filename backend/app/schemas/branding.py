"""Schemas da marca do escritório (Fase 7 — personalização: nome + logo)."""

from pydantic import BaseModel, Field


class BrandingOut(BaseModel):
    nome_escritorio: str | None = None
    tem_logo: bool = False
    logo_mime: str | None = None
    # plano permite personalizar? (flag 'logo') — o front trava a seção e mostra upsell se False.
    pode_personalizar: bool = False


class BrandingUpdate(BaseModel):
    # None = limpar o nome. max_length casa com a coluna usada no cabeçalho do PDF.
    nome_escritorio: str | None = Field(default=None, max_length=120)
