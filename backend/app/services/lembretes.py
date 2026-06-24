"""Motor de LEMBRETES comerciais (apontamentos do agente sobre o funil de oportunidades).

DESENHO (o que torna o 3B viável): as REGRAS determinísticas em Python detectam a situação e já
montam um apontamento completo e útil (severidade, categoria, ref, mensagem-base). O LLM é só um
humanizador opcional por-item (ver ollama_client) — se desligado/lento, fica a mensagem-base.

Tudo o que é número/comparação de data sai do SQL (com fuso fixo, p/ não deslocar 1 dia quando o
servidor está em UTC). O Python só aplica as regras sobre as colunas já computadas — função PURA
(`_avaliar`), testável sem banco. RLS escopa as linhas ao dono (tenant) na própria sessão.

"contato realizado" não tem campo dedicado no modelo: o proxy é o ÚLTIMO toque registrado =
COALESCE(MAX(comentario.created_at), oportunidade.created_at). Por isso as regras de "esfriando"/
"proposta parada" falam em "sem REGISTRO de contato" (mede ausência de comentário, não de conversa).
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.services import ollama_client

# Último toque = COALESCE(último comentário, criação) — mesmo proxy em todas as regras.
# Datas comparadas no fuso configurado (não no UTC cru do servidor).
_SQL = """
select
  o.id, o.nome, o.etapa, o.obra_id,
  o.contato_telefone, o.contato_email, o.valor_estimado, o.proximo_followup, o.seq_humano,
  (lc.ultimo_comentario is not null) as tem_comentario,
  case when o.proximo_followup is null then null
       else ((now() at time zone :tz)::date - o.proximo_followup) end as dias_followup,
  ((now() at time zone :tz)::date
     - (coalesce(lc.ultimo_comentario, o.created_at) at time zone :tz)::date) as dias_sem_toque,
  ((now() at time zone :tz)::date
     - (o.updated_at at time zone :tz)::date) as dias_desde_update
from public.oportunidades o
left join lateral (
  select max(c.created_at) as ultimo_comentario
  from public.oportunidade_comentarios c
  where c.oportunidade_id = o.id
) lc on true
where o.etapa <> 'perdido'
"""

_SEV_RANK = {"alta": 0, "media": 1, "baixa": 2}


def _fmt_brl(v: float) -> str:
    """'R$ 50.000' (sem libs de locale)."""
    return "R$ " + f"{v:,.0f}".replace(",", ".")


def _ap(
    r: dict,
    regra_id: str,
    categoria: str,
    severidade: str,
    titulo: str,
    mensagem: str,
    sugestao: str | None,
    dias: int | None,
) -> dict:
    return {
        "id_oportunidade": r["id"],
        "seq_humano": r["seq_humano"],
        "nome": r["nome"],
        "regra_id": regra_id,
        "categoria": categoria,
        "severidade": severidade,
        "etapa": r["etapa"],
        "contato_telefone": r["contato_telefone"],
        "contato_email": r["contato_email"],
        "dias": dias,
        "titulo": titulo,
        "mensagem": mensagem,
        "sugestao": sugestao,
        "humanizado": False,
    }


def _avaliar(rows: list[dict], cfg: Settings) -> list[dict]:
    """Regras puras → no máx. 1 apontamento por oportunidade (a de maior severidade)."""
    out: list[dict] = []
    for r in rows:
        etapa = r["etapa"]
        ativo = etapa not in ("ganho", "perdido")  # 'perdido' já fora do SQL
        df = r["dias_followup"]
        dst = r["dias_sem_toque"]
        tel = (r["contato_telefone"] or "").strip()
        email = (r["contato_email"] or "").strip()
        cands: list[tuple[int, dict]] = []  # (ordem-da-regra, apontamento)

        if ativo and df is not None and df > 0:
            cands.append((1, _ap(
                r, "R1", "followup", "alta", "Follow-up atrasado",
                f"Follow-up atrasado há {df} dia(s).", "Retomar o contato hoje.", df)))
        if etapa == "proposta" and dst >= cfg.LEMBRETES_DIAS_PROPOSTA:
            cands.append((2, _ap(
                r, "R5", "proposta", "alta", "Proposta parada",
                f"Proposta enviada e sem registro de contato há {dst} dias.",
                "Confirmar se o cliente recebeu e decidiu.", dst)))
        if (etapa == "lead" and not r["tem_comentario"] and r["proximo_followup"] is None
                and dst >= cfg.LEMBRETES_DIAS_LEAD_NOVO):
            cands.append((3, _ap(
                r, "R4", "lead", "alta", "Lead sem primeiro contato",
                f"Lead criado há {dst} dias e ainda sem nenhum contato registrado.",
                "Fazer o primeiro contato.", dst)))
        if ativo and df == 0:
            cands.append((4, _ap(
                r, "R2", "followup", "media", "Follow-up hoje",
                "Follow-up agendado para hoje.", "Falar com o cliente hoje.", 0)))
        if ativo and dst >= cfg.LEMBRETES_DIAS_ESFRIANDO:
            cands.append((5, _ap(
                r, "R3", "esfriando", "media", "Oportunidade esfriando",
                f"Sem registro de contato há {dst} dias — pode estar esfriando.",
                "Dar um retorno ao cliente.", dst)))
        if (ativo and r["proximo_followup"] is None and r["valor_estimado"] is not None
                and float(r["valor_estimado"]) >= cfg.LEMBRETES_VALOR_ALTO):
            cands.append((6, _ap(
                r, "R6", "followup", "media", "Alto valor sem follow-up",
                f"Oportunidade de {_fmt_brl(float(r['valor_estimado']))} sem próximo follow-up "
                "agendado.", "Agendar o próximo contato.", None)))
        if (etapa == "ganho" and r["obra_id"] is None
                and r["dias_desde_update"] >= cfg.LEMBRETES_DIAS_GANHO):
            cands.append((7, _ap(
                r, "R8", "conversao", "media", "Ganho sem obra",
                f"Marcada como ganho há {r['dias_desde_update']} dias e ainda não virou obra.",
                "Converter em obra.", r["dias_desde_update"])))
        if ativo and not tel and not email:
            cands.append((8, _ap(
                r, "R7", "dados", "baixa", "Contato sem canal",
                "Sem telefone e sem e-mail cadastrados.", "Adicionar um canal de contato.", None)))

        if cands:
            cands.sort(key=lambda c: (_SEV_RANK[c[1]["severidade"]], c[0]))
            out.append(cands[0][1])
    return out


def _ordena(aps: list[dict]) -> list[dict]:
    """Maior severidade primeiro; dentro da severidade, o mais 'vencido' (mais dias) primeiro."""
    aps.sort(key=lambda a: (_SEV_RANK[a["severidade"]], -(a["dias"] or 0)))
    return aps


async def _humanizar(aps: list[dict], cfg: Settings) -> None:
    """Best-effort: reescreve só os N mais relevantes via 3B; o resto fica na mensagem-base."""
    if not cfg.lembretes_llm_ativo:
        return
    for a in aps[: cfg.LEMBRETES_LLM_MAX_ITENS]:
        res = await ollama_client.humanizar_item(a)
        if res:
            a["mensagem"] = res["frase"]
            if res.get("sugestao"):
                a["sugestao"] = res["sugestao"]
            a["humanizado"] = True


async def _buscar(session: AsyncSession, tz: str) -> list[dict]:
    rows = (await session.execute(text(_SQL), {"tz": tz})).all()
    return [dict(r._mapping) for r in rows]


async def listar_apontamentos(session: AsyncSession) -> list[dict]:
    """Apontamentos do funil (RLS escopa ao dono). Regras determinísticas + humanização opcional."""
    cfg = get_settings()
    rows = await _buscar(session, cfg.LEMBRETES_TZ)
    aps = _ordena(_avaliar(rows, cfg))
    await _humanizar(aps, cfg)
    return aps
