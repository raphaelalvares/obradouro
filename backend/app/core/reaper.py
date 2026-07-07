"""Reaper do export (Fase 8 — durabilidade). Loop in-process que re-dispara jobs de export órfãos.

POR QUÊ: o worker do export roda via FastAPI BackgroundTasks (in-process, 1 worker uvicorn, depois
da resposta). Se o processo reinicia/deploya/cai/OOM antes ou durante o worker, o job fica preso em
'pendente'/'processando' sem nada que o retome — era o "na fila há 1 mês". Este loop varre
periodicamente (funções SECURITY DEFINER cross-tenant da migration 0110, já que o reaper roda como
cria_app sem JWT) e reprocessa. O 1º sweep é no boot: pega tudo que ficou órfão no último deploy.

CICLO DE VIDA: sobe no lifespan (main.py) só FORA de teste. 1 worker → 1 reaper; o claim atômico +
o guard _EM_VOO do serviço mantêm tudo idempotente mesmo se um dia escalar para vários processos.
"""

import asyncio
import logging

from app.core.config import get_settings
from app.services import export

log = logging.getLogger("cria.export")


async def reaper_loop() -> None:
    """1º sweep imediato (órfãos do último deploy) + a cada EXPORT_REAPER_INTERVAL_SECONDS. Cada
    volta é isolada: uma falha loga e o loop segue no próximo ciclo (nunca morre por um erro)."""
    interval = get_settings().EXPORT_REAPER_INTERVAL_SECONDS
    while True:
        try:
            falhados, redisparados = await export.reaper_tick()
            if falhados:
                log.warning("reaper: %d export(s) marcados 'erro' (excederam tentativas)", falhados)
            if redisparados:
                log.warning("reaper: %d export(s) travado(s) re-disparado(s)", redisparados)
        except asyncio.CancelledError:
            raise  # shutdown: propaga p/ o loop encerrar limpo
        except Exception:  # noqa: BLE001
            log.exception("reaper: ciclo falhou (segue no próximo)")
        await asyncio.sleep(interval)
