"""Offload de trabalho CPU-bound do event loop (1 worker uvicorn) + teto de concorrência.

POR QUÊ: o backend roda **1 worker** (1 event loop). Chamar PIL/fpdf/openpyxl direto dentro de um
handler `async` TRAVA o loop — enquanto processa 1 upload/PDF, todos os outros requests param (até o
health check). `run_cpu` joga a função síncrona numa thread (`asyncio.to_thread`): como PIL/zlib/
libjpeg liberam a GIL no trabalho em C, o loop volta a aceitar e responder requests durante o
processamento, mesmo com 1 vCPU.

O SEMÁFORO limita quantas dessas operações pesadas rodam ao mesmo tempo. Cada uma carrega o arquivo
inteiro + buffers de pixel na RAM; sem teto, um pico de uploads/exports estoura a memória do
container (4 GB) e/ou enfileira no pool de conexões do DB. Tunável por `HEAVY_OPS_CONCURRENCY`.

REGRA DE OURO (evita starvation do pool): chame `run_cpu` **sem segurar uma conexão de banco**. Se
uma conexão ficar aberta enquanto se espera o semáforo, um pico de operações pesadas tranca o pool
inteiro. Nos uploads de foto (alto volume) o processamento roda FORA da transação por isso (ver
`anexos.upload` + `db_context`).
"""

import asyncio
from collections.abc import Callable

from app.core.config import get_settings

_sem = asyncio.Semaphore(get_settings().HEAVY_OPS_CONCURRENCY)


async def run_cpu[T](func: Callable[..., T], /, *args, **kwargs) -> T:
    """Roda `func(*args, **kwargs)` (CPU-bound, síncrona) numa thread, sob o teto de concorrência.

    Propaga exceções normalmente (inclusive HTTPException / UnsupportedImage)."""
    async with _sem:
        return await asyncio.to_thread(func, *args, **kwargs)
