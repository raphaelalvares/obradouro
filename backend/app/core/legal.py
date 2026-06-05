"""Versões vigentes dos documentos legais (Termos de Uso / Política de Privacidade).

O backend carimba ESTA versão ao registrar o aceite (app.services.aceites). Ao publicar um texto
novo, suba a versão correspondente → o app pode exigir re-aceite (decisão de produto/jurídica).
Mantenha em sincronia com os documentos servidos em web/public/legal/.
"""

TERMOS_VERSAO = "2026-06-04"
PRIVACIDADE_VERSAO = "2026-06-04"

# documento → versão vigente. As chaves casam com as rotas públicas do front (/termos|/privacidade).
DOCUMENTOS: dict[str, str] = {
    "termos": TERMOS_VERSAO,
    "privacidade": PRIVACIDADE_VERSAO,
}
