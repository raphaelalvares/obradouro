"""Schemas do aceite de documentos legais (Termos/Privacidade)."""

import datetime as dt
from typing import Literal

from pydantic import BaseModel


class AceiteOut(BaseModel):
    documento: str
    versao: str
    origem: str | None = None
    aceito_em: dt.datetime


class DocumentoVersaoOut(BaseModel):
    documento: str
    versao: str


class AceiteRegistrarIn(BaseModel):
    # contexto: 'cadastro' = atestado no metadata do signup; 'gate' = aceite explícito no app.
    origem: Literal["cadastro", "gate"] = "gate"
