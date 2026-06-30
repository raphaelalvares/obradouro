"""Schemas do assistente conversacional (chat)."""

from typing import Literal

from pydantic import BaseModel, Field


class MensagemChat(BaseModel):
    papel: Literal["user", "assistant"]
    conteudo: str = Field(min_length=1, max_length=4000)


class AssistenteIn(BaseModel):
    mensagem: str = Field(min_length=1, max_length=2000)
    historico: list[MensagemChat] | None = None


class AssistenteOut(BaseModel):
    resposta: str
    disponivel: bool = False  # false = Ollama off/erro (resposta é o fallback determinístico)
    pendencias_count: int = 0
