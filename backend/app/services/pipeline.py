"""Pipeline do projeto (linha do tempo de 9 etapas fixas). Ver migration 0097.

`listar` é para arquiteto E cliente (membros): semeia as etapas no read do arquiteto, lê a tabela e
DERIVA `acao_pendente` de cada gate cruzando o estado vivo (revisão pendente / orçamento enviado /
orçamento aprovado), via a RPC definer `pipeline_gates` (o cliente não lê orcamento_versoes direto).
`atualizar_etapa` é do arquiteto; `decidir_iniciar_obra` é do cliente (RPC definer).
"""

import json
import uuid

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.audit import log_event
from app.services.common import actor_name, projeto_member, projeto_writable

# (código, rótulo pt-BR, gate). Ordem = posição na lista (1..9). FIXO (decisão do usuário).
_ETAPAS: list[tuple[str, str, str | None]] = [
    ("medicao", "Agendamento de medição", None),
    ("base", "Planta base", None),
    ("layouts", "Layouts", "revisao"),
    ("projeto_3d", "Projeto 3D", None),
    ("apresentacao", "Apresentação", None),
    ("aprovacao", "Aprovação do projeto", "revisao"),
    ("manual", "Manual do proprietário", None),
    ("orcamento", "Orçamento da obra (EVF)", "proposta"),
    ("iniciar_obra", "Início da obra", "iniciar_obra"),
]
ROTULOS = {c: r for c, r, _ in _ETAPAS}
GATES = {c: g for c, _, g in _ETAPAS}
ORDEM = {c: i + 1 for i, (c, _, _) in enumerate(_ETAPAS)}
_STATUS_VALIDOS = {"a_fazer", "em_andamento", "aguardando_cliente", "concluida"}


def _acao_pendente(codigo: str, etapa: dict, gates: dict) -> bool:
    """Há ação do cliente esperando neste gate? (deriva do estado vivo)."""
    gate = GATES.get(codigo)
    if gate == "revisao":
        return bool(gates.get("rev_pendente"))
    if gate == "proposta":
        return bool(gates.get("orc_pendente"))
    if gate == "iniciar_obra":
        return etapa.get("decisao") is None and bool(gates.get("orc_aprovado"))
    return False


def _monta(etapa: dict, gates: dict) -> dict:
    codigo = etapa["etapa"]
    return {
        "etapa": codigo,
        "rotulo": ROTULOS.get(codigo, codigo),
        "ordem": etapa.get("ordem") or ORDEM.get(codigo, 99),
        "status": etapa.get("status") or "a_fazer",
        "data_prevista": etapa.get("data_prevista"),
        "concluida_em": etapa.get("concluida_em"),
        "decisao": etapa.get("decisao"),
        "observacao": etapa.get("observacao"),
        "gate": GATES.get(codigo),
        "acao_pendente": _acao_pendente(codigo, etapa, gates),
    }


async def listar(session: AsyncSession, projeto_id: uuid.UUID) -> dict:
    await projeto_member(session, projeto_id)  # 404 se não-membro
    # semeadura preguiçosa: qualquer membro ativo semeia (a RPC gateia por meu_papel_projeto) — o
    # cliente também vê a timeline materializada num projeto antigo que o arquiteto não abriu.
    await session.execute(
        text("select public.garantir_etapas_projeto(cast(:p as uuid))"),
        {"p": str(projeto_id)},
    )
    rows = (
        await session.execute(
            text(
                """select etapa, ordem, status, data_prevista, concluida_em, decisao, observacao
                   from public.projeto_etapas where projeto_id = cast(:p as uuid) order by ordem"""
            ),
            {"p": str(projeto_id)},
        )
    ).all()
    # fallback p/ projeto antigo não semeado (cliente lendo antes do arquiteto): defaults read-only
    etapas = (
        [dict(r._mapping) for r in rows]
        if rows
        else [{"etapa": c, "ordem": ORDEM[c], "status": "a_fazer"} for c, _, _ in _ETAPAS]
    )
    raw = (
        await session.execute(
            text("select public.pipeline_gates(cast(:p as uuid))"), {"p": str(projeto_id)}
        )
    ).scalar_one_or_none()
    gates = (json.loads(raw) if isinstance(raw, str) else raw) or {}
    out = [_monta(e, gates) for e in etapas]
    atual = next(
        (e["etapa"] for e in out if e["status"] != "concluida"),
        out[-1]["etapa"] if out else None,
    )
    return {"etapas": out, "etapa_atual": atual}


async def atualizar_etapa(
    session: AsyncSession,
    user_id: str,
    projeto_id: uuid.UUID,
    etapa: str,
    *,
    novo_status: str | None = None,
    data_prevista=None,
    observacao: str | None = None,
    set_data: bool = False,
    set_obs: bool = False,
) -> dict:
    """Arquiteto avança a etapa. `set_data`/`set_obs` distinguem 'não enviado' de 'enviado None'."""
    cur = await projeto_writable(session, projeto_id)
    if etapa not in ROTULOS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "etapa inexistente")
    sets, params = [], {"p": str(projeto_id), "e": etapa}
    if novo_status is not None:
        if novo_status not in _STATUS_VALIDOS:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "status inválido")
        sets.append("status = cast(:s as public.status_etapa)")
        params["s"] = novo_status
        sets.append("concluida_em = case when :s = 'concluida' then now() else null end")
    if set_data:
        sets.append("data_prevista = :d")
        params["d"] = data_prevista
    if set_obs:
        sets.append("observacao = :o")
        params["o"] = observacao
    if sets:
        # garante a etapa semeada (idempotente) antes de atualizar — cobre projeto antigo
        await session.execute(
            text("select public.garantir_etapas_projeto(cast(:p as uuid))"),
            {"p": str(projeto_id)},
        )
        await session.execute(
            text(
                f"update public.projeto_etapas set {', '.join(sets)} "
                "where projeto_id = cast(:p as uuid) "
                "and etapa = cast(:e as public.etapa_projeto)"
            ),
            params,
        )
        await log_event(
            session,
            tenant=cur.tenant_id,
            actor_id=user_id,
            obra_id=None,
            projeto_id=projeto_id,
            action="projeto.etapa_atualizada",
            entity_type="projeto",
            entity_id=projeto_id,
            changed={k: (str(v) if k in ("d",) else v) for k, v in params.items()
                     if k not in ("p", "e")},
            entity_label=cur.nome,
            entity_seq=cur.seq_humano,
            actor_label=await actor_name(session),
        )
    return await listar(session, projeto_id)


async def decidir_iniciar_obra(
    session: AsyncSession, projeto_id: uuid.UUID, decisao: str
) -> dict:
    """Cliente decide iniciar a obra (sim/não). RPC definer valida papel/expiry e audita. Mapeia os
    erros da RPC (sqlstate) p/ HTTP — espelha decidir_proposta (orcamentos.py)."""
    try:
        await session.execute(
            text("select public.decidir_iniciar_obra(cast(:p as uuid), :d)"),
            {"p": str(projeto_id), "d": decisao},
        )
    except DBAPIError as e:
        sqlstate = getattr(getattr(e, "orig", None), "sqlstate", None)
        if sqlstate == "42501":  # não é cliente ativo (ou acesso vencido)
            raise HTTPException(status.HTTP_403_FORBIDDEN, "apenas o cliente decide") from e
        if sqlstate == "P0002":  # pipeline ainda não preparado p/ este projeto
            raise HTTPException(status.HTTP_404_NOT_FOUND, "etapa não encontrada") from e
        if sqlstate == "22023":
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "decisão inválida") from e
        raise
    return await listar(session, projeto_id)
