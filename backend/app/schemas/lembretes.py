"""Schemas dos LEMBRETES comerciais (apontamentos do agente sobre o funil)."""

import uuid
from typing import Literal

from pydantic import BaseModel


class ApontamentoOut(BaseModel):
    """Um lembrete pronto p/ exibir. `mensagem` é a humanizada (se `humanizado`) ou a baseline da
    regra. `dias` = número relevante da regra (atraso, dias sem toque…); None se não couber."""

    id_oportunidade: uuid.UUID
    seq_humano: int | None = None
    nome: str
    regra_id: str  # ex.: 'R1'
    categoria: str  # followup | proposta | esfriando | lead | conversao | dados
    severidade: Literal["alta", "media", "baixa"]
    etapa: str
    contato_telefone: str | None = None
    contato_email: str | None = None
    dias: int | None = None
    titulo: str
    mensagem: str
    sugestao: str | None = None
    humanizado: bool = False
