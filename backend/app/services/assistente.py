"""Assistente conversacional do CRIA — chat sobre os dados do usuário (comercial, no 1º corte).

FILOSOFIA (igual aos lembretes): o LLM é só a camada de LINGUAGEM. O Python monta um SNAPSHOT
determinístico do comercial (funil + pendências + oportunidades) e o 3B responde SOMENTE com base
nele — não inventa número/nome/data. Read-only, tenant-scoped (RLS). PRECISA do Ollama ligado
(ASSISTENTE_ENABLED); sem ele degrada com uma resposta determinística que lista as pendências.

EXTENSÃO ("em tudo"): hoje o que o assistente "sabe estar pendente" vem do comercial (_pendencias →
lembretes). Plugar obras/orçamento/cronograma aqui = o chat passa a conhecê-los, sem mudança.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.schemas.assistente import AssistenteIn
from app.services import lembretes, ollama_client
from app.services import oportunidades as op_svc

_SYSTEM = (
    "Você é o assistente do CRIA, um sistema de gestão de obra para arquitetos. Responda em "
    "português do Brasil, de forma curta e direta, SOMENTE com base no CONTEXTO abaixo (dados "
    "reais do usuário). Se a resposta não estiver no contexto, diga que ainda não tem essa "
    "informação — NUNCA invente números, nomes ou datas. Para o que está em aberto/pendente, "
    "use a seção Pendências."
)


def _brl(v) -> str:
    return "R$ " + f"{float(v or 0):,.0f}".replace(",", ".")


async def _pendencias(session: AsyncSession) -> list[dict]:
    """O que o assistente conhece como 'em aberto'. Hoje só comercial; ponto de extensão futuro."""
    return await lembretes.coletar_apontamentos(session)


def _montar_snapshot(ops: list[dict], pend: list[dict], cfg: Settings) -> str:
    abertos = [o for o in ops if o["etapa"] not in ("ganho", "perdido")]
    ganhos = [o for o in ops if o["etapa"] == "ganho"]
    perdidos = [o for o in ops if o["etapa"] == "perdido"]
    valor_aberto = sum(float(o["valor_estimado"] or 0) for o in abertos)
    valor_ganho = sum(float(o["valor_estimado"] or 0) for o in ganhos)

    linhas = [
        "Funil comercial:",
        f"- {len(abertos)} oportunidade(s) em aberto, {_brl(valor_aberto)} em negociação",
        f"- {len(ganhos)} ganha(s) ({_brl(valor_ganho)}), {len(perdidos)} perdida(s)",
        "",
        f"Pendências ({len(pend)}):",
    ]
    if pend:
        for a in pend[: cfg.ASSISTENTE_MAX_OPORTUNIDADES]:
            seq = f"#{a['seq_humano']}" if a["seq_humano"] is not None else ""
            linhas.append(f"- [{a['severidade']}] {a['nome']} {seq}: {a['mensagem']}")
        if len(pend) > cfg.ASSISTENTE_MAX_OPORTUNIDADES:
            linhas.append(f"- (+{len(pend) - cfg.ASSISTENTE_MAX_OPORTUNIDADES} mais)")
    else:
        linhas.append("- (nada pendente)")

    linhas += ["", f"Oportunidades ({len(ops)}):"]
    for o in ops[: cfg.ASSISTENTE_MAX_OPORTUNIDADES]:
        seq = f"#{o['seq_humano']}" if o["seq_humano"] is not None else ""
        contato = o["contato_nome"] or "—"
        fu = o["proximo_followup"] or "—"
        linhas.append(
            f"- {seq} {o['nome']} · etapa={o['etapa']} · contato={contato} · "
            f"valor={_brl(o['valor_estimado'])} · follow-up={fu}"
        )
    if len(ops) > cfg.ASSISTENTE_MAX_OPORTUNIDADES:
        linhas.append(f"- (+{len(ops) - cfg.ASSISTENTE_MAX_OPORTUNIDADES} não listadas)")
    return "\n".join(linhas)


def _fallback(pend: list[dict]) -> str:
    base = "O assistente de conversa está indisponível (modelo local desligado). "
    if not pend:
        return base + "Você não tem pendências no funil agora."
    itens = "; ".join(f"{a['nome']} ({a['mensagem']})" for a in pend[:5])
    return base + f"Você tem {len(pend)} pendência(s): {itens}."


def _mensagens(snapshot: str, data: AssistenteIn, cfg: Settings) -> list[dict]:
    msgs = [{"role": "system", "content": f"{_SYSTEM}\n\nCONTEXTO:\n{snapshot}"}]
    historico = (data.historico or [])[-cfg.ASSISTENTE_MAX_HISTORICO:]
    for m in historico:
        papel = "assistant" if m.papel == "assistant" else "user"
        msgs.append({"role": papel, "content": m.conteudo})
    msgs.append({"role": "user", "content": data.mensagem})
    return msgs


async def responder(session: AsyncSession, data: AssistenteIn) -> dict:
    cfg = get_settings()
    pend = await _pendencias(session)
    if not cfg.assistente_ativo:
        return {"resposta": _fallback(pend), "disponivel": False, "pendencias_count": len(pend)}
    ops = await op_svc.list_oportunidades(session)
    snapshot = _montar_snapshot(ops, pend, cfg)
    resposta = await ollama_client.conversar(_mensagens(snapshot, data, cfg))
    if resposta is None:
        return {"resposta": _fallback(pend), "disponivel": False, "pendencias_count": len(pend)}
    return {"resposta": resposta, "disponivel": True, "pendencias_count": len(pend)}
