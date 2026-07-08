"""Rate limiting em memória (defesa-em-profundidade) p/ os endpoints de bootstrap de credencial.

O backend roda **1 worker uvicorn** (1 event loop), então um contador em memória por-processo é
suficiente e dispensa lock: `hit()` é síncrono (sem `await` no meio → nenhuma corrotina interleava
entre a leitura e a escrita do contador). NÃO é distribuído — escalar p/ N workers exigiria um store
compartilhado (Redis) OU o rate limit no edge (Traefik — ver docs/infra-edge-hardening.md). A 1ª
linha continua sendo o edge + os limites do próprio GoTrue (p/ os quais o backend passa o IP real do
cliente); esta é a rede de segurança da aplicação nos endpoints de auth.

Algoritmo: janela deslizante por LOG (guarda os timestamps das batidas por chave e evita os velhos).
Preciso e barato p/ o volume de auth. A deque nunca cresce além de `limit` (batidas negadas NÃO são
gravadas). O número de chaves distintas tem teto DURO em `_MAX_KEYS`: ao encher, poda as expiradas
se ainda cheio (todas ativas), remove a menos-recente (LRU) — assim um flood de IPs/emails forjados
não cresce a memória sem limite nem degrada o custo por inserção.
"""

import time
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class Decision:
    allowed: bool
    retry_after: int  # segundos até liberar (0 quando allowed)


class SlidingWindowLimiter:
    """Limitador por chave, janela deslizante. Não-thread-safe de propósito (1 event loop)."""

    _MAX_KEYS = 10_000  # teto de chaves distintas p/ conter flood de IPs/emails forjados

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}

    def hit(self, key: str, *, limit: int, window_s: float, now: float | None = None) -> Decision:
        """Registra uma batida e decide. `now` é injetável p/ teste (senão usa time.monotonic())."""
        t = time.monotonic() if now is None else now
        dq = self._hits.get(key)
        if dq is None:
            if len(self._hits) >= self._MAX_KEYS:
                self._prune(t, window_s)
                while len(self._hits) >= self._MAX_KEYS:  # teto DURO: todas ativas → despeja a LRU
                    self._evict_lru()
            dq = self._hits.setdefault(key, deque())
        cutoff = t - window_s
        while dq and dq[0] <= cutoff:
            dq.popleft()
        if len(dq) >= limit:
            # bloqueado: a batida mais antiga expira em dq[0] + window_s → é quando libera.
            retry = int(dq[0] + window_s - t) + 1
            return Decision(allowed=False, retry_after=max(retry, 1))
        dq.append(t)
        return Decision(allowed=True, retry_after=0)

    def _prune(self, now: float, window_s: float) -> None:
        """Descarta chaves cuja janela esvaziou (chamado quando o dict atinge o teto)."""
        cutoff = now - window_s
        for k in list(self._hits.keys()):
            dq = self._hits[k]
            while dq and dq[0] <= cutoff:
                dq.popleft()
            if not dq:
                del self._hits[k]

    def _evict_lru(self) -> None:
        """Poda não liberou espaço (todas as chaves ativas) → remove a menos-recente (menor último
        timestamp). Garante o teto DURO e limita o custo. As deques aqui nunca estão vazias
        (o _prune acabou de remover as vazias)."""
        victim = min(self._hits, key=lambda k: self._hits[k][-1])
        del self._hits[victim]


# Instância global do processo (1 worker uvicorn) — reusada pelas rotas de auth.
auth_limiter = SlidingWindowLimiter()
