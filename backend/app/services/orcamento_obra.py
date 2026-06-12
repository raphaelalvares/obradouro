"""'Virar obra': semeia o CHECKLIST da obra a partir de uma versão do orçamento.

Fecha a cadeia comercial → execução: as linhas do orçamento (etapa → serviço, com cômodo/qtd/
unidade) viram etapas + itens do checklist da obra. Reusa a RPC `importar_checklist` (0026/0043/
0044: dedupe por nome_norm, seq sem queimar, audit por linha) — re-rodar NÃO duplica o que já
existe. Obra alvo = a vinculada ao projeto; sem vínculo, cria via RPC `criar_obra` (id dual-ID
vindo do cliente) e vincula (espelha oportunidades.converter).

NÃO leva CUSTOS p/ o checklist: custo do checklist é visível ao CLIENTE da obra (get_tree só mascara
p/ prestador) — gravar o custo cru do orçamento ali vazaria a margem (o cliente que viu o preço de
VENDA na proposta deduziria custo×linha). Semeia só a ESTRUTURA de trabalho (etapa / serviço /
cômodo / unidade / quantidade); o custo segue só no módulo de orçamento (arquiteto-only).
"""

import json
import uuid

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.problems import limite_from_exc
from app.services import ambientes as ambientes_svc
from app.services import checklist_import
from app.services import orcamentos as orc_svc
from app.services.audit import log_event
from app.services.common import actor_name, obra_writable, projeto_writable
from app.services.orcamentos import _map_42501

_OBRA_COLS = "id, nome, status, seq_humano, created_at"


def _payload_do_orcamento(itens: list[dict]) -> list[dict]:
    """Linhas do orçamento → payload da RPC importar_checklist (PURA, testável; sem ids — o service
    injeta). Agrupa por etapa (nome; ordem = menor ordem_etapa, como _agrupar_etapas). Leva só a
    ESTRUTURA (nome/cômodo/unidade/quantidade) — SEM custos (não vazar margem; ver docstring do
    módulo). O dedupe do checklist é (etapa, nome_norm): mesmo serviço em cômodos diferentes ganha o
    sufixo '(cômodo)' p/ não colapsar; duplicata restante é descartada (a RPC pularia igual)."""
    grupos: dict[str, dict] = {}
    for it in itens:
        en = checklist_import.norm_nome(it["etapa"])
        if not en:
            continue
        g = grupos.get(en)
        if g is None:
            grupos[en] = g = {
                "nome": it["etapa"], "nome_norm": en, "ordem": it["ordem_etapa"], "_itens": []
            }
        else:
            g["ordem"] = min(g["ordem"], it["ordem_etapa"])
        g["_itens"].append(it)

    out = []
    for g in sorted(grupos.values(), key=lambda g: (g["ordem"], g["nome_norm"])):
        # nomes repetidos na MESMA etapa (cômodos diferentes) → desambigua com o cômodo no nome
        contagem: dict[str, int] = {}
        for it in g["_itens"]:
            nn = checklist_import.norm_nome(it["descricao"])
            contagem[nn] = contagem.get(nn, 0) + 1
        vistos: set[str] = set()
        itens_out = []
        for it in g["_itens"]:
            nome = it["descricao"]
            nn = checklist_import.norm_nome(nome)
            if contagem.get(nn, 0) > 1 and it.get("ambiente"):
                nome = f"{nome} ({it['ambiente']})"
                nn = checklist_import.norm_nome(nome)
            if not nn or nn in vistos:
                continue
            vistos.add(nn)
            itens_out.append(
                {
                    "nome": nome,
                    "nome_norm": nn,
                    "ordem": len(itens_out) + 1,
                    "ambiente": it.get("ambiente"),
                    "unidade": it.get("unidade"),
                    "quantidade": (
                        float(it["quantidade"]) if it.get("quantidade") is not None else None
                    ),
                }
            )
        out.append(
            {"nome": g["nome"], "nome_norm": g["nome_norm"], "ordem": g["ordem"],
             "itens": itens_out}
        )
    return out


async def virar_obra(
    session: AsyncSession,
    user_id: str,
    projeto_id: uuid.UUID,
    versao_id: uuid.UUID,
    obra_id_novo: uuid.UUID,
) -> dict:
    cur = await projeto_writable(session, projeto_id)  # arquiteto do projeto
    v = await orc_svc._versao_row(session, projeto_id, versao_id)  # 404 se não é deste projeto
    itens = await orc_svc._itens_da_versao(session, versao_id)
    if not itens:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "este orçamento ainda não tem serviços — adicione itens antes de virar obra",
        )

    nome_ator = await actor_name(session)
    vinc = (
        await session.execute(
            text("select obra_id from public.projetos where id = cast(:p as uuid)"),
            {"p": str(projeto_id)},
        )
    ).first()
    obra_id = vinc.obra_id if vinc else None
    obra_criada = False

    if obra_id is None:
        # cria a obra (RPC atômica: obra + vínculo de arquiteto; soft-limit do plano → 403 limpo)
        try:
            obra = (
                await session.execute(
                    text(f"select {_OBRA_COLS} from public.criar_obra(cast(:id as uuid), :nome)"),
                    {"id": str(obra_id_novo), "nome": cur.nome},
                )
            ).first()
        except DBAPIError as e:
            err = limite_from_exc(e)  # P0001 'limite_obras_ativas:...' → soft-limit (403)
            if err is not None:
                raise err from e
            raise (_map_42501(e) or e) from e
        if obra is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "não foi possível criar a obra")
        obra_id, obra_nome, obra_seq = obra.id, obra.nome, obra.seq_humano
        obra_criada = True
        try:
            await session.execute(
                text(
                    "update public.projetos set obra_id = cast(:o as uuid) "
                    "where id = cast(:p as uuid)"
                ),
                {"o": str(obra_id), "p": str(projeto_id)},
            )
        except DBAPIError as e:
            raise (_map_42501(e) or e) from e
        await log_event(
            session, tenant=cur.tenant_id, actor_id=user_id, obra_id=obra_id,
            action="obra.criada", entity_type="obra", entity_id=obra_id,
            entity_label=obra_nome, entity_seq=obra_seq, actor_label=nome_ator,
        )
        await log_event(
            session, tenant=cur.tenant_id, actor_id=user_id, obra_id=obra_id,
            projeto_id=projeto_id, action="projeto.obra_vinculada", entity_type="projeto",
            entity_id=projeto_id, changed={"obra_id": str(obra_id)},
            entity_label=cur.nome, entity_seq=cur.seq_humano, actor_label=nome_ator,
        )
    else:
        cur_obra = await obra_writable(session, obra_id)  # 403 se não é arquiteto da obra
        obra_nome, obra_seq = cur_obra.nome, cur_obra.seq_humano

    payload = _payload_do_orcamento(itens)
    for e in payload:  # UUID por nó (como checklist.importar; usado só se a linha for nova)
        e["id"] = str(uuid.uuid4())
        for it in e["itens"]:
            it["id"] = str(uuid.uuid4())
    try:
        row = (
            await session.execute(
                text(
                    """
                    select etapas_novas, etapas_existentes, itens_novos, itens_existentes
                    from public.importar_checklist(cast(:o as uuid), cast(:p as jsonb))
                    """
                ),
                {"o": str(obra_id), "p": json.dumps(payload)},
            )
        ).first()
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    resumo = dict(row._mapping)
    # a RPC grava o cômodo como TEXTO; liga ao registro (cria cômodos novos + seta ambiente_id)
    await ambientes_svc.reconciliar(session, obra_id, cur.tenant_id)

    await log_event(
        session, tenant=cur.tenant_id, actor_id=user_id, obra_id=obra_id,
        action="checklist.importado", entity_type="obra", entity_id=obra_id,
        changed=resumo, entity_label=obra_nome, entity_seq=obra_seq, actor_label=nome_ator,
    )
    await log_event(
        session, tenant=cur.tenant_id, actor_id=user_id, obra_id=obra_id, projeto_id=projeto_id,
        action="orcamento.virou_obra", entity_type="orcamento_versao", entity_id=versao_id,
        changed={"obra_id": str(obra_id), "obra_criada": obra_criada, **resumo},
        entity_label=f"Orçamento R{v.numero}", entity_seq=v.seq_humano, actor_label=nome_ator,
    )
    return {
        "obra_id": obra_id,
        "obra_nome": obra_nome,
        "obra_seq": obra_seq,
        "obra_criada": obra_criada,
        **resumo,
    }
