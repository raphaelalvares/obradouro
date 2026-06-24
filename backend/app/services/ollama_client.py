"""Cliente fino do LLM LOCAL (Ollama) — humaniza os lembretes comerciais.

BEST-EFFORT por design (espelha notificacoes.py): NUNCA levanta para quem chama. Se a flag está off,
o Ollama não responde, estoura o timeout ou devolve JSON fora do schema, retorna None — e o serviço
de lembretes cai na mensagem-base da regra. O modelo (qwen2.5:3b) é pequeno: o papel dele é só
COSMÉTICO (reescrever 1 fato em 1 frase), nunca decidir severidade/categoria. Como o Ollama é
on-prem, o dado (nome/contato) não sai da máquina; um LLM remoto exigiria revisão de privacidade.
"""

import json
import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Schema da saída forçado no Ollama (campo `format`): o 3B sempre devolve JSON estruturalmente
# válido; o limite é a qualidade do texto, por isso pedimos pouco (1 frase + 1 sugestão curtas).
_FORMAT = {
    "type": "object",
    "properties": {
        "frase": {"type": "string", "maxLength": 160},
        "sugestao": {"type": "string", "maxLength": 90},
    },
    "required": ["frase", "sugestao"],
    "additionalProperties": False,
}

_SYSTEM = (
    "Você reescreve UM lembrete comercial para um arquiteto. Receba 1 fato e devolva 1 frase "
    "amigável e curta + 1 sugestão curta de ação. Português do Brasil, tom direto, sem emojis, "
    "sem inventar dados (use só o que está no fato). Responda só o JSON."
)


def _prompt(fato: dict) -> str:
    nome = fato["nome"]
    return (
        f'Fato: {fato["titulo"]} | oportunidade "{nome}" | etapa={fato["etapa"]} | '
        f'dias={fato.get("dias")} | categoria={fato["categoria"]} | '
        f'severidade={fato["severidade"]}\n'
        f'Baseline (referencia, nao copie literal): {fato["mensagem"]}\n'
        "Saida: frase (comece pelo que precisa de atencao) + "
        'sugestao (1 acao curta no imperativo, ex.: "Ligar hoje").'
    )


async def humanizar_item(fato: dict) -> dict | None:
    """Reescreve 1 lembrete via Ollama. {'frase','sugestao'} ou None (caller usa a baseline)."""
    settings = get_settings()
    if not settings.lembretes_llm_ativo:
        return None
    payload = {
        "model": settings.OLLAMA_MODEL,
        "system": _SYSTEM,
        "prompt": _prompt(fato),
        "stream": False,
        "format": _FORMAT,
        "options": {"temperature": 0.2, "num_predict": 120},
    }
    try:
        timeout = httpx.Timeout(settings.OLLAMA_TIMEOUT_S)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{settings.OLLAMA_URL.rstrip('/')}/api/generate", json=payload
            )
            resp.raise_for_status()
            body = resp.json()
        data = json.loads(body.get("response") or "{}")
        frase = (data.get("frase") or "").strip()
        sugestao = (data.get("sugestao") or "").strip()
        if not frase:
            return None
        return {"frase": frase, "sugestao": sugestao or None}
    except Exception:  # noqa: BLE001 — best-effort: nunca propaga (cai na baseline da regra)
        logger.exception("falha ao humanizar lembrete via Ollama")
        return None
