"""Avanço físico / curva S (Fatia C) — DERIVADO do checklist (sem tabela).

Unidade = FOLHA AGENDADA (item sem filhos com data_inicio E data_fim). Na EAP de 4 níveis a folha
carrega o trabalho (custo/estado/datas); os agregadores derivam. Peso = custo (quando a obra tem
custos; senão contagem — 1 por folha). A folha está "concluída" quando estado='concluido' (data =
sua conclusão). Curva (ambas baseadas em TÉRMINO, comparáveis):
  planejado(D) = Σ peso das folhas com data_fim <= D ;  real(D) = Σ peso das concluídas até D.
"""

import datetime as dt

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.common import obra_member


def _pct(parte: float, total: float) -> float:
    return round(min(parte / total, 1.0) * 100, 1) if total > 0 else 0.0


def curva_s(tarefas: list[dict], hoje: dt.date) -> dict:
    """Função PURA (testável). `tarefas`: dicts com peso_custo(float|None), data_inicio(date),
    data_fim(date), concluido(bool), concluido_em(date|None) e, opcionalmente, medicoes (lista de
    {data: date, pct: float} — o avanço SNAPSHOT datado do diário). Datas obrigatórias (o chamador
    filtra as agendadas). Com medições o "real" vira ponderado por % (não binário); sem medição, cai
    no concluido/concluido_em (retrocompatível). Devolve avanço atual + a série da curva S."""
    vazio = {
        "por_custo": False, "peso_total": 0.0, "real_pct": 0.0, "planejado_pct": 0.0,
        "inicio": None, "fim": None, "pontos": [],
    }
    if not tarefas:
        return vazio

    # por custo SÓ se TODAS as tarefas têm custo > 0 (obra totalmente orçada). Obra MISTA (alguma
    # sem valor) ou custo sujo (0/negativo) → cai p/ contagem: senão a tarefa de peso 0 sumiria da
    # curva e esconderia progresso real.
    por_custo = all((t["peso_custo"] or 0.0) > 0 for t in tarefas)
    for t in tarefas:
        t["_peso"] = (t["peso_custo"] or 0.0) if por_custo else 1.0
        # medições do diário (SNAPSHOT datado): [(data, fração 0..1)] crescente por data. Com elas,
        # "real" da folha em D é a ÚLTIMA medição até D; sem elas, cai p/ o binário do estado.
        meds = sorted(
            (
                (m["data"], max(0.0, min(1.0, (m["pct"] or 0.0) / 100.0)))
                for m in (t.get("medicoes") or [])
            ),
            key=lambda md: md[0],
        )
        t["_meds"] = meds
        # concluída sem data (anomalia) → conta como concluída HOJE. Só como fallback da folha SEM
        # medição (a folha medida usa _meds, que já cravam o 100% na data da medição).
        t["_concl_em"] = (t["concluido_em"] or hoje) if (t["concluido"] and not meds) else None
    peso_total = sum(t["_peso"] for t in tarefas)
    if peso_total <= 0:  # rede de segurança (por_custo=all>0 já garante > 0; contagem → N>=1)
        return {**vazio, "por_custo": por_custo}

    def _real_frac(t: dict, d: dt.date) -> float:
        """Fração realizada (0..1) da folha em D: última medição até D, ou o binário do estado."""
        if t["_meds"]:
            frac = 0.0
            for md, mf in t["_meds"]:
                if md <= d:
                    frac = mf
                else:
                    break
            return frac
        ce = t["_concl_em"]
        return 1.0 if (ce is not None and ce <= d) else 0.0

    inicio = min(t["data_inicio"] for t in tarefas)
    fim_plan = max(t["data_fim"] for t in tarefas)  # término PLANEJADO (planejado=100% aqui)

    def acum(d: dt.date) -> tuple[float, float]:
        plan = sum(t["_peso"] for t in tarefas if t["data_fim"] <= d)
        real = sum(t["_peso"] * _real_frac(t, d) for t in tarefas)
        return plan, real

    # degraus exatos da curva real = datas de conclusão (fallback) + datas de medição.
    # o eixo vai até o término planejado OU até hoje/o evento mais tardio (atraso conclui depois).
    eventos = [t["_concl_em"] for t in tarefas if t["_concl_em"] is not None]
    eventos += [md for t in tarefas for (md, _) in t["_meds"]]
    fim_eixo = max([fim_plan, *([hoje] if hoje >= inicio else []), *eventos])

    # passo: semanal, mas afrouxa em obras longas p/ manter a série leve (<= ~110 pontos).
    passo = max(7, (fim_eixo - inicio).days // 100 + 1)
    datas: set[dt.date] = {inicio, fim_plan, fim_eixo}
    datas.update(eventos)  # degraus exatos da curva real
    if hoje >= inicio:
        datas.add(hoje)
    cur = inicio
    while cur < fim_eixo:
        datas.add(cur)
        cur += dt.timedelta(days=passo)
    pontos = []
    for d in sorted(datas):
        plan, real = acum(d)
        pontos.append(
            {"data": d, "planejado_pct": _pct(plan, peso_total), "real_pct": _pct(real, peso_total)}
        )

    plan_hoje, real_hoje = acum(hoje)  # "agora": não clampar (conclusão após o fim previsto conta)
    return {
        "por_custo": por_custo,
        "peso_total": round(peso_total, 2),
        "real_pct": _pct(real_hoje, peso_total),
        "planejado_pct": _pct(plan_hoje, peso_total),
        "inicio": inicio,
        "fim": fim_eixo,  # fim do EIXO (>= término planejado); o chart escala por aqui
        "pontos": pontos,
    }


async def avanco(session: AsyncSession, obra_id, hoje: dt.date | None = None) -> dict:
    """Lê as FOLHAS agendadas (item sem filhos com data_inicio E data_fim) e suas MEDIÇÕES do diário
    e monta a curva S. Na EAP de 4 níveis a folha é a unidade de trabalho; agregadores derivam. O
    "real" usa o histórico de medições (curva de progresso de verdade); folha sem medição cai no
    estado/concluido_em (retrocompatível)."""
    await obra_member(session, obra_id)  # qualquer membro ativo vê o avanço
    rows = (
        await session.execute(
            text(
                """
                select t.id, t.data_inicio, t.data_fim, t.custo_total, t.estado, t.concluido_em
                from public.checklist_itens t
                where t.obra_id = cast(:o as uuid)
                  and not exists (select 1 from public.checklist_itens c
                                  where c.parent_item_id = t.id)
                  and t.data_inicio is not null and t.data_fim is not null
                """
            ),
            {"o": str(obra_id)},
        )
    ).all()
    # medições (avanço por tarefa) de TODAS as tarefas da obra, datadas pela data do diário, em
    # ordem (data, created_at) → a última de uma data ganha como SNAPSHOT daquela data.
    med_rows = (
        await session.execute(
            text(
                """
                select dt.item_id, d.data, dt.progresso_pct
                from public.diario_tarefas dt
                join public.diario_obra d on d.id = dt.diario_id
                where dt.obra_id = cast(:o as uuid)
                order by d.data, dt.created_at
                """
            ),
            {"o": str(obra_id)},
        )
    ).all()
    meds_por_item: dict = {}
    for m in med_rows:
        meds_por_item.setdefault(m.item_id, []).append(
            {"data": m.data, "pct": float(m.progresso_pct)}
        )
    # etapa/subetapa que são FOLHA-COM-CUSTO (custo em qualquer nível): não têm checklist_item, logo
    # não saem na query de folhas acima nem têm medição no diário. Entram com peso = custo_total e
    # progresso BINÁRIO pelo marco `concluida`. Só agendadas (com datas), como as tarefas-folha.
    etapa_folhas = (
        await session.execute(
            text(
                """
                select e.data_inicio, e.data_fim, e.custo_total, e.concluida, e.concluida_em
                from public.etapas e
                where e.obra_id = cast(:o as uuid)
                  and e.custo_total is not null
                  and e.data_inicio is not null and e.data_fim is not null
                  and not exists (select 1 from public.subetapas s where s.etapa_id = e.id)
                  and not exists (select 1 from public.checklist_itens c where c.etapa_id = e.id)
                """
            ),
            {"o": str(obra_id)},
        )
    ).all()
    subetapa_folhas = (
        await session.execute(
            text(
                """
                select s.data_inicio, s.data_fim, s.custo_total, s.concluida, s.concluida_em
                from public.subetapas s
                where s.obra_id = cast(:o as uuid)
                  and s.custo_total is not null
                  and s.data_inicio is not null and s.data_fim is not null
                  and not exists (select 1 from public.checklist_itens c where c.subetapa_id = s.id)
                """
            ),
            {"o": str(obra_id)},
        )
    ).all()
    tarefas = []
    for r in rows:
        d = dict(r._mapping)
        cem = d["concluido_em"]
        tarefas.append(
            {
                "peso_custo": float(d["custo_total"]) if d["custo_total"] is not None else None,
                "data_inicio": d["data_inicio"],
                "data_fim": d["data_fim"],
                "concluido": d["estado"] == "concluido",
                "concluido_em": cem.date() if cem is not None else None,
                "medicoes": meds_por_item.get(d["id"], []),
            }
        )
    for r in (*etapa_folhas, *subetapa_folhas):
        d = dict(r._mapping)
        cem = d["concluida_em"]
        tarefas.append(
            {
                "peso_custo": float(d["custo_total"]),
                "data_inicio": d["data_inicio"],
                "data_fim": d["data_fim"],
                "concluido": bool(d["concluida"]),
                "concluido_em": cem.date() if cem is not None else None,
                "medicoes": [],
            }
        )
    return curva_s(tarefas, hoje or dt.date.today())
