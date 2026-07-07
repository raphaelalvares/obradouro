"""Interface do backend de armazenamento de BYTES (Fase 4).

Decisão travada do roteiro: o storage fica ATRÁS de um módulo, com interface trocável
(guardar/recuperar/deletar/medir/empacotar/expurgar). Trocar o backend (disco → Google Drive →
S3/Supabase) NÃO deve exigir mexer fora deste pacote. No modelo API-only, o byte SEMPRE trafega
pelo Python: browser → API (multipart) → StorageBackend → API (stream) → browser. Nenhum app fala
com o storage direto.

Mapeamento dos 6 verbos do roteiro para os primitivos abaixo:
  guardar  → guardar            recuperar → recuperar
  deletar  → deletar/deletar_prefixo (expurgo real de um objeto/prefixo)
  medir    → tamanho            empacotar → composto (listar_chaves + recuperar) na Fase 8
  expurgar → deletar_prefixo

Chaves (`key`) são OPACAS para o resto da app: o service guarda a string em anexos.storage_key e
nunca interpreta seu formato. Aqui adotamos um caminho lógico tipo
``<tenant>/<obra>/<anexo>/full.<ext>`` — namespacing por anexo facilita a reconciliação (varrer um
prefixo) e o expurgo (Fase 8).
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class StorageBackend(Protocol):
    """Contrato mínimo de um backend de bytes. Métodos assíncronos (não bloqueiam o event loop)."""

    async def guardar(self, key: str, data: bytes, content_type: str) -> None:
        """Grava `data` sob `key` (sobrescreve). Deve ser atômico o suficiente p/ não deixar
        arquivo meio-escrito visível (ex.: escrever em temp + rename)."""
        ...

    async def recuperar(self, key: str) -> bytes:
        """Lê os bytes de `key`. Levanta FileNotFoundError se a chave não existe (service → 404)."""
        ...

    async def deletar(self, key: str) -> None:
        """Remove `key`. Idempotente (não falha se já não existe)."""
        ...

    async def existe(self, key: str) -> bool:
        """True se a chave existe."""
        ...

    async def tamanho(self, key: str) -> int | None:
        """Tamanho em bytes de `key`, ou None se não existe (medir/reconciliar)."""
        ...

    async def listar_chaves(self, prefix: str) -> list[str]:
        """Todas as chaves sob `prefix` (reconciliação Fase 4 e empacotar Fase 8)."""
        ...

    async def deletar_prefixo(self, prefix: str) -> int:
        """Remove tudo sob `prefix` (expurgo de um anexo/obra). Retorna quantas chaves removeu."""
        ...

    # ---- capacidades OPCIONAIS (painel admin de armazenamento). Backends que não sabem medir a
    # ---- CONTA (ex.: disco local) devolvem None em espaco_conta; uso_prefixo_bytes é a soma real.
    async def espaco_conta(self) -> dict | None:
        """Espaço da CONTA de storage inteira (não por-tenant), p/ o painel admin mostrar o 'livre
        real'. dict com bytes: {'total_bytes' (None=ilimitado), 'usado_bytes' (tudo — no Drive isso
        inclui Gmail/Fotos), 'usado_drive_bytes', 'lixeira_bytes'}; ou None se o backend não sabe
        medir a conta (disco local). Fonte CORRETA do espaço físico — não somar chave a chave."""
        ...

    async def uso_prefixo_bytes(self, prefix: str) -> int | None:
        """Soma REAL (recursiva, pastas+subpastas) dos bytes sob `prefix`, medida no backend —
        inclui miniaturas, então tende a ser MAIOR que o contabilizado (que conta só o 'full').
        Cara (varre a árvore) → uso pontual de reconciliação. None se indisponível."""
        ...
