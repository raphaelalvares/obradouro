"""Helpers de resposta HTTP."""

from urllib.parse import quote


def content_disposition(nome: str, *, inline: bool = True) -> str:
    """Monta um Content-Disposition seguro (RFC 6266) a partir de um nome vindo do usuário.

    B8: o nome do arquivo NÃO pode ser interpolado cru em ``filename="..."`` — um ``"`` (ou ``\\``)
    no nome quebraria a delimitação do parâmetro. Emitimos o ``filename=`` ASCII com aspas/barras
    neutralizadas (fallback p/ clients antigos) E o ``filename*=UTF-8''`` percent-encoded (RFC 5987)
    p/ preservar acento/unicode. CR/LF já são removidos no sanitize do upload → não há header
    injection; isto fecha só a confusão de parâmetro.
    """
    disp = "inline" if inline else "attachment"
    ascii_name = nome.encode("ascii", "ignore").decode("ascii")
    ascii_name = ascii_name.replace("\\", "_").replace('"', "_").strip() or "arquivo"
    return f"{disp}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(nome, safe='')}"
