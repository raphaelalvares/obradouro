"""Middleware de segurança (ASGI puro — robusto inclusive com respostas em streaming).

- M5: rejeita o corpo da requisição que excede o teto, ANTES de a aplicação lê-lo (defesa-em-
  profundidade contra DoS de memória/disco por upload gigante). É a 2ª linha — a 1ª é o limite no
  edge/reverse-proxy (Traefik), ver docs/infra-edge-hardening.md. Dois cortes: (1) rápido, pelo
  header Content-Length (uploads multipart sempre o enviam); (2) fino, CONTANDO os bytes enquanto o
  app lê o corpo — pega `Transfer-Encoding: chunked`/sem Content-Length (e um Content-Length
  mentiroso). Estourou → 413 (memória limitada ao teto, nunca ao corpo inteiro).
- M8: injeta `X-Content-Type-Options: nosniff` em TODA resposta (cobre a mídia servida pela API —
  evita content-sniffing de um anexo malicioso). Idempotente (não duplica se já houver).
- B6 (CsrfMiddleware): protege requisições cookie-auth (BFF) contra CSRF (double-submit).
"""

import secrets
from collections.abc import Awaitable, Callable
from http.cookies import SimpleCookie

Scope = dict
Message = dict
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]

# B6: nomes dos cookies/header (espelham app.core.security/auth_cookies — repetidos aqui p/ o
# middleware não acoplar ao resto e ficar barato no hot-path).
_ACCESS_COOKIE = "cria_access"
_REFRESH_COOKIE = "cria_refresh"
_CSRF_COOKIE = "cria_csrf"
_CSRF_HEADER = b"x-csrf-token"
_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
# Rotas que BOOTSTRAPAM credencial (login/cadastro): não dependem de cookie ambiente, então o
# double-submit não as protege; e exigir CSRF nelas TRAVA o re-login quando um cria_access velho
# ficou preso (cookie httpOnly que o JS não limpa). Por isso são isentas. str.endswith aceita tupla.
_CSRF_EXEMPT_SUFFIXES = ("/auth/login", "/auth/signup")


class _BodyTooLarge(Exception):
    """Corpo passou do teto durante o streaming (M5 fino). Capturada no __call__."""


class SecurityMiddleware:
    def __init__(self, app, *, max_body_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        # M5 (rápido): corte por Content-Length antes de qualquer leitura do corpo.
        for name, value in scope.get("headers") or []:
            if name == b"content-length":
                try:
                    if int(value) > self.max_body_bytes:
                        await self._too_large(send)
                        return
                except ValueError:
                    pass
                break

        # M5 (fino): conta os bytes enquanto o app lê o corpo (chunked / sem Content-Length, ou com
        # um Content-Length mentiroso). Estourou → levanta _BodyTooLarge (capturada abaixo). Este
        # middleware roda FORA do ExceptionMiddleware do Starlette → a exceção volta limpa até aqui.
        seen = 0
        started = False

        async def counting_receive() -> Message:
            nonlocal seen
            message = await receive()
            if message.get("type") == "http.request":
                seen += len(message.get("body") or b"")
                if seen > self.max_body_bytes:
                    raise _BodyTooLarge
            return message

        # M8: acrescenta nosniff no início da resposta (funciona com bytes e streaming).
        async def send_wrapper(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                headers = message.setdefault("headers", [])
                if not any(k.lower() == b"x-content-type-options" for k, _ in headers):
                    headers.append((b"x-content-type-options", b"nosniff"))
            await send(message)

        try:
            await self.app(scope, counting_receive, send_wrapper)
        except _BodyTooLarge:
            # Caso normal: o app lê o corpo ANTES de responder → a resposta ainda não começou e dá
            # p/ mandar o 413 limpo. Se já tinha começado (app que faz stream da resposta enquanto
            # lê o corpo — não há no app), só interrompe: não dá p/ trocar o status no meio.
            if not started:
                await self._too_large(send)

    @staticmethod
    async def _too_large(send: Send) -> None:
        body = b'{"detail":"corpo da requisicao excede o limite"}'
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"x-content-type-options", b"nosniff"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


class CsrfMiddleware:
    """B6 (BFF): protege requisições cookie-auth contra CSRF (double-submit).

    Age quando há cookie de SESSÃO (access OU refresh) e o método muda estado: exige o header
    X-CSRF-Token igual ao cookie cria_csrf. O token CSRF só chega ao front pelo CORPO do
    login/refresh/session (a SOP impede lê-lo cross-site), então um POST forjado não casa o header.

    Gatear TAMBÉM por cria_refresh fecha o vão de /auth/refresh e /auth/logout: após o access (~1h)
    expirar, o refresh+csrf (janela de inatividade) seguem vivos e um POST cross-site a /refresh
    pulava o double-submit. Como o front, após um reload, perde o token em memória, ele o re-hidrata
    por GET /auth/csrf (seguro, isento) ANTES do /refresh. cria_refresh tem path /…/auth, então o
    gate extra só pega as rotas /auth (não o resto da API, que só carrega cria_access).

    Passam direto: requisições só-Bearer (legado, sem cookie) e server-to-server como o webhook do
    Stripe (sem cookie); os métodos seguros (GET/HEAD/OPTIONS); e o bootstrap de credencial
    (/auth/login, /auth/signup — ver _CSRF_EXEMPT_SUFFIXES).
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http" or scope.get("method") not in _UNSAFE_METHODS:
            await self.app(scope, receive, send)
            return

        if scope.get("path", "").endswith(_CSRF_EXEMPT_SUFFIXES):  # login/cadastro: isentos
            await self.app(scope, receive, send)
            return

        headers = scope.get("headers") or []
        cookie_hdr = next((v for k, v in headers if k == b"cookie"), b"")
        cookies = SimpleCookie()
        cookies.load(cookie_hdr.decode("latin-1"))

        # sem cookie de sessão (nem access nem refresh) → não é cookie-auth → CSRF não se aplica
        if _ACCESS_COOKIE not in cookies and _REFRESH_COOKIE not in cookies:
            await self.app(scope, receive, send)
            return

        csrf_cookie = cookies.get(_CSRF_COOKIE)
        csrf_header = next((v for k, v in headers if k == _CSRF_HEADER), None)
        ok = (
            csrf_cookie is not None
            and csrf_header is not None
            and secrets.compare_digest(csrf_cookie.value, csrf_header.decode("latin-1"))
        )
        if not ok:
            await self._forbidden(send)
            return
        await self.app(scope, receive, send)

    @staticmethod
    async def _forbidden(send: Send) -> None:
        body = b'{"detail":"CSRF token invalido ou ausente"}'
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"x-content-type-options", b"nosniff"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
