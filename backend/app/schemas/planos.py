"""Schemas de plano/quota."""

from pydantic import BaseModel


class ObrasAtivasQuota(BaseModel):
    em_uso: int
    limite: int  # -1 = ilimitado


class QuotaOut(BaseModel):
    plano: str
    obras_ativas: ObrasAtivasQuota
    pode_criar_obra: bool
    flags: dict
