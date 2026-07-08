"""Serviço de export "em camadas" (Fase 8 — portabilidade LGPD).

Fluxo: o arquiteto pede (`solicitar`) → cria um job 'pendente' → a rota agenda `processar` em
background → o worker abre a PRÓPRIA sessão com o contexto RLS do tenant (lê só os dados dele),
monta o .zip e grava no storage → status 'pronto' por 30 dias → `baixar` serve os bytes → após o
prazo, `expurgar_vencidos` apaga os bytes de verdade (status 'expirado').

Async sem fila dedicada (v1): FastAPI BackgroundTasks roda após a resposta, no mesmo processo —
suficiente p/ o volume inicial; trocar por fila real (Celery/RQ) não muda este contrato. O job vive
no banco (sobrevive como registro e pode ser repolido).
"""

import logging
import uuid

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.concurrency import run_cpu
from app.core.config import get_settings
from app.core.database import SessionLocal, _set_rls_context
from app.services import export_pacote as pacote
from app.services.common import actor_name
from app.services.storage import get_storage

_log = logging.getLogger("cria.export")
_JOB_COLS = "id, status, tamanho_bytes, erro, pronto_em, expira_em, created_at, updated_at"
_RETENCAO_DIAS = 30

# ids sendo processados NESTE processo (1 worker). Guard barato e exato p/ o caso comum: impede que
# o reaper (ou um re-POST) redispare um job que já está rodando aqui — o claim atômico no banco é a
# trava real, isto só evita trabalho e uma 2ª cópia das fotos na RAM. Zera num restart (aí o lease
# do 'processando' assume: o worker morreu → o reaper reprocessa após EXPORT_PROCESSANDO_LEASE).
_EM_VOO: set[str] = set()


async def _job_by_id(session: AsyncSession, job_id) -> dict | None:
    row = (
        await session.execute(
            text(
                f"select {_JOB_COLS} from public.export_jobs "
                "where id = cast(:j as uuid) and tenant_id = (select auth.uid())"
            ),
            {"j": str(job_id)},
        )
    ).first()
    return dict(row._mapping) if row else None


async def expurgar_vencidos(session: AsyncSession) -> int:
    """Apaga do storage os .zip vencidos do tenant corrente e marca 'expirado' (expurgo REAL)."""
    vencidos = (
        await session.execute(
            text(
                "select id, zip_key from public.export_jobs "
                "where tenant_id = (select auth.uid()) and status = 'pronto' "
                "and expira_em is not null and expira_em < now()"
            )
        )
    ).all()
    storage = get_storage()
    for j in vencidos:
        if j.zip_key:
            await storage.deletar(j.zip_key)  # idempotente
        await session.execute(
            text(
                "update public.export_jobs set status = 'expirado', zip_key = null "
                "where id = :j"
            ),
            {"j": j.id},
        )
    return len(vencidos)


async def listar(session: AsyncSession) -> list[dict]:
    await expurgar_vencidos(session)
    rows = (
        await session.execute(
            text(
                f"select {_JOB_COLS} from public.export_jobs "
                "where tenant_id = (select auth.uid()) order by created_at desc limit 20"
            )
        )
    ).all()
    return [dict(r._mapping) for r in rows]


async def get_job(session: AsyncSession, job_id: uuid.UUID) -> dict:
    job = await _job_by_id(session, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "export não encontrado")
    return job


async def solicitar(session: AsyncSession) -> dict:
    """Cria um job de export. Se já houver um em andamento, devolve o mesmo (sem duplicar)."""
    await expurgar_vencidos(session)
    em_andamento = (
        await session.execute(
            text(
                f"select {_JOB_COLS} from public.export_jobs "
                "where tenant_id = (select auth.uid()) and status in ('pendente', 'processando') "
                "order by created_at desc limit 1"
            )
        )
    ).first()
    if em_andamento is not None:
        return dict(em_andamento._mapping)

    job_id = str(uuid.uuid4())
    await session.execute(
        text(
            "insert into public.export_jobs (id, tenant_id, status) "
            "values (cast(:j as uuid), (select auth.uid()), 'pendente')"
        ),
        {"j": job_id},
    )
    return await get_job(session, job_id)


async def baixar(session: AsyncSession, job_id: uuid.UUID) -> tuple[bytes, str]:
    row = (
        await session.execute(
            text(
                "select status, zip_key, expira_em from public.export_jobs "
                "where id = cast(:j as uuid) and tenant_id = (select auth.uid())"
            ),
            {"j": str(job_id)},
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "export não encontrado")
    if row.status != "pronto" or not row.zip_key:
        raise HTTPException(status.HTTP_409_CONFLICT, "export ainda não está pronto")
    try:
        data = await get_storage().recuperar(row.zip_key)
    except FileNotFoundError as e:
        raise HTTPException(
            status.HTTP_410_GONE, "arquivo do export não está mais disponível"
        ) from e
    return data, f"obradouro-dados-{str(job_id)[:8]}.zip"


# ============================ worker (background) ============================
async def _coletar(session: AsyncSession) -> tuple[list[dict], list[tuple[str, str]]]:
    """Lê os dados do tenant corrente e devolve (obras_spec, fotos_keys). obras_spec já traz os CSV
    montados; fotos_keys = [(caminho_no_zip, storage_key)] para o worker buscar os bytes depois."""
    obras = (
        await session.execute(
            text(
                "select id, nome, seq_humano from public.obras "
                "where tenant_id = (select auth.uid()) order by seq_humano"
            )
        )
    ).all()

    obras_spec: list[dict] = []
    fotos_keys: list[tuple[str, str]] = []
    for o in obras:
        pasta = f"obra-{o.seq_humano or '0'}-{pacote.slug(o.nome)}"
        oid = {"o": str(o.id)}

        check_rows = (
            await session.execute(
                text(
                    """
                    select e.seq_humano as etapa_seq, e.nome as etapa,
                           s.nome as subetapa,
                           case when i.parent_item_id is null then 'tarefa' else 'sub' end as nivel,
                           i.nome as item, i.estado, i.ambiente, i.unidade, i.quantidade,
                           i.valor_unitario, i.custo_total,
                           p.nome as concluido_por, i.concluido_em
                    from public.etapas e
                    join public.checklist_itens i on i.etapa_id = e.id
                    left join public.subetapas s on s.id = i.subetapa_id
                    left join public.profiles p on p.id = i.concluido_por
                    where e.obra_id = cast(:o as uuid)
                    order by e.ordem, e.seq_humano,
                             s.ordem nulls last, s.seq_humano nulls last,
                             i.parent_item_id nulls first, i.ordem, i.seq_humano
                    """
                ),
                oid,
            )
        ).all()

        estoque_rows = (
            await session.execute(
                text(
                    """
                    select n.numero as nf, n.emitente_nome as fornecedor, n.data_chegada,
                           coalesce(nullif(it.nome_editado, ''), it.descricao) as item,
                           it.unidade, it.quantidade_nota, it.quantidade_conferida,
                           it.valor_unitario, it.valor_total
                    from public.nota_itens it
                    join public.notas_fiscais n on n.id = it.nota_id
                    where it.obra_id = cast(:o as uuid)
                    order by n.numero, it.ordem
                    """
                ),
                oid,
            )
        ).all()

        anexos = (
            await session.execute(
                text(
                    "select id, seq_humano, nome_arquivo, storage_key from public.anexos "
                    "where obra_id = cast(:o as uuid) order by created_at, seq_humano"
                ),
                oid,
            )
        ).all()
        for a in anexos:
            ident = a.seq_humano if a.seq_humano is not None else str(a.id)[:8]
            nome = a.nome_arquivo or "foto"
            fotos_keys.append((f"{pasta}/fotos/{ident}-{nome}", a.storage_key))

        obras_spec.append(
            {
                "pasta": pasta,
                "checklist_csv": pacote.csv_checklist([dict(r._mapping) for r in check_rows]),
                "estoque_csv": pacote.csv_estoque([dict(r._mapping) for r in estoque_rows]),
            }
        )

    return obras_spec, fotos_keys


async def _set_status(claims: dict, job_id: str, **campos) -> None:
    """Grava o RESULTADO do job (pronto/erro) numa transação própria (worker fora do ciclo de
    request). As chaves de `campos` são fixas/controladas (status, zip_key, tamanho_bytes, erro) —
    valores vão por bind. Só escreve se o job ainda está 'processando' (este worker é o dono da
    vez): num double-run improvável, o perdedor casa 0 linhas e não sobrescreve o do vencedor."""
    sets = ", ".join(f"{k} = :{k}" for k in campos)
    if campos.get("status") == "pronto":  # libera por 30 dias a partir de agora
        sets += f", pronto_em = now(), expira_em = now() + interval '{_RETENCAO_DIAS} days'"
    async with SessionLocal() as session:
        async with session.begin():
            await _set_rls_context(session, claims, background=True)
            await session.execute(
                text(
                    f"update public.export_jobs set {sets} "
                    "where id = cast(:j as uuid) and tenant_id = (select auth.uid()) "
                    "and status = 'processando'"
                ),
                {**campos, "j": job_id},
            )


async def _claim(claims: dict, job_id: str) -> bool:
    """Pega o job ATOMICAMENTE (1ª ação do worker) e incrementa `tentativas`. Retorna True se ESTE
    worker ganhou. Idempotente entre o dispatch inline e o reaper: um único UPDATE casa a linha
    'pendente' (ou 'processando' com o lease vencido → worker morreu) e a passa a 'processando'.
    Ao atingir EXPORT_MAX_TENTATIVAS o UPDATE não casa mais (anti job-veneno; o reaper depois marca
    'erro')."""
    s = get_settings()
    async with SessionLocal() as session:
        async with session.begin():
            await _set_rls_context(session, claims, background=True)
            row = (
                await session.execute(
                    text(
                        "update public.export_jobs "
                        "set status = 'processando', tentativas = tentativas + 1 "
                        "where id = cast(:j as uuid) and tenant_id = (select auth.uid()) "
                        "and tentativas < :max "
                        "and (status = 'pendente' "
                        "     or (status = 'processando' "
                        "         and updated_at < now() "
                        "             - (cast(:lease as int) * interval '1 second'))) "
                        "returning id"
                    ),
                    {
                        "j": job_id,
                        "max": s.EXPORT_MAX_TENTATIVAS,
                        "lease": s.EXPORT_PROCESSANDO_LEASE_SECONDS,
                    },
                )
            ).first()
    return row is not None


async def processar(job_id: str, claims: dict) -> None:
    """Entrada do worker (dispatch inline via BackgroundTasks OU reaper). Pega o job (claim
    atômico), monta o .zip e grava no storage. Best-effort: em erro, marca 'erro'. Sai cedo (sem
    trabalho) se já está rodando aqui (_EM_VOO) ou se perdeu o claim (outro pegou / não é
    reprocessável / estourou tentativas). `gerado_em` vem do banco (now())."""
    if job_id in _EM_VOO:
        return
    if not await _claim(claims, job_id):
        return
    _EM_VOO.add(job_id)
    try:
        async with SessionLocal() as session:
            async with session.begin():
                await _set_rls_context(session, claims, background=True)
                obras_spec, fotos_keys = await _coletar(session)
                gerado_em = (
                    await session.execute(text("select to_char(now(), 'DD/MM/YYYY HH24:MI')"))
                ).scalar()
                quem = await actor_name(session)

        storage = get_storage()
        fotos: list[tuple[str, bytes]] = []
        for caminho, key in fotos_keys:
            try:
                fotos.append((caminho, await storage.recuperar(key)))
            except FileNotFoundError:
                continue  # foto sumiu do storage: segue sem ela (best-effort)

        cabecalho = f"{gerado_em}" + (f" — {quem}" if quem else "")
        zip_bytes = await run_cpu(pacote.montar_zip, obras_spec, fotos, cabecalho)
        # chave DETERMINÍSTICA (mesmo valor pelo caminho inline e pelo reaper: claims['sub'] == o
        # tenant_id do job) → um reprocesso sobrescreve o .zip anterior, nunca deixa órfão.
        zip_key = f"exports/{claims['sub']}/{job_id}.zip"
        await storage.guardar(zip_key, zip_bytes, "application/zip")

        await _set_status(
            claims, job_id, status="pronto", zip_key=zip_key, tamanho_bytes=len(zip_bytes)
        )
    except Exception:  # noqa: BLE001 — registra a falha no job em vez de sumir no background
        # NÃO devolver str(e) ao cliente (vaza detalhe interno: driver, chave de storage, etc.).
        # O erro completo vai só pro log do servidor; o campo visível ao dono recebe msg genérica.
        _log.exception("export job %s falhou", job_id)
        await _set_status(
            claims, job_id, status="erro", erro="falha ao gerar o pacote; tente novamente"
        )
    finally:
        _EM_VOO.discard(job_id)


# ============================ reaper (durabilidade) ============================
# O reaper roda como cria_app SEM contexto de RLS (não tem JWT), então varre/aposenta via funções
# SECURITY DEFINER (migration 0110). Só o reprocesso (processar → _claim) reidrata o contexto
# 'authenticated' do tenant por-job.
async def _jobs_travados() -> list[tuple[str, str]]:
    """(job_id, tenant_id) dos jobs de export travados, cross-tenant. Limitado (EXPORT_REAPER_BATCH)
    p/ não estourar a RAM num pico (cada reprocesso carrega as fotos todas)."""
    s = get_settings()
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                text(
                    "select id, tenant_id from public.export_jobs_reap(:grace, :lease, :max, :lim)"
                ),
                {
                    "grace": s.EXPORT_PENDENTE_GRACE_SECONDS,
                    "lease": s.EXPORT_PROCESSANDO_LEASE_SECONDS,
                    "max": s.EXPORT_MAX_TENTATIVAS,
                    "lim": s.EXPORT_REAPER_BATCH,
                },
            )
        ).all()
    return [(str(r.id), str(r.tenant_id)) for r in rows]


async def _falhar_excedidos() -> int:
    """Aposenta como 'erro' os jobs EXAUSTOS e TRAVADOS (a função exige frescor além do teto de
    tentativas, p/ não marcar 'erro' um job sendo processado com êxito). Retorna quantos."""
    s = get_settings()
    async with SessionLocal() as session:
        async with session.begin():
            n = (
                await session.execute(
                    text("select public.export_jobs_falhar_excedidos(:max, :grace, :lease)"),
                    {
                        "max": s.EXPORT_MAX_TENTATIVAS,
                        "grace": s.EXPORT_PENDENTE_GRACE_SECONDS,
                        "lease": s.EXPORT_PROCESSANDO_LEASE_SECONDS,
                    },
                )
            ).scalar()
    return int(n or 0)


async def redirecionar_travados() -> int:
    """Re-dispara os jobs de export órfãos (worker morreu/deploy). SEQUENCIAL de propósito: cada
    reprocesso carrega todas as fotos do tenant na RAM — dois ao mesmo tempo estouram o container.
    Cada job é isolado (try/except só-log): uma falha nunca aborta o lote. O claim atômico + _EM_VOO
    garantem que nada roda em dobro. Retorna quantos foram re-disparados."""
    travados = await _jobs_travados()
    for job_id, tenant_id in travados:
        try:
            await processar(job_id, {"sub": tenant_id, "email": None})
        except Exception:  # noqa: BLE001
            _log.exception("reaper: falha ao reprocessar export %s", job_id)
    return len(travados)


async def reaper_tick() -> tuple[int, int]:
    """Uma passada do reaper: aposenta os que excederam tentativas e re-dispara os travados.
    Retorna (marcados_erro, re_disparados) para o loop logar."""
    falhados = await _falhar_excedidos()
    redisparados = await redirecionar_travados()
    return falhados, redisparados
