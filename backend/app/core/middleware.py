"""Middleware de segurança (ASGI puro — robusto inclusive com respostas em streaming).

- M5: rejeita o corpo da requisição que excede o teto, ANTES de a aplicação lê-lo (defesa-em-
  profundidade contra DoS de memória/disco por upload gigante). É a 2ª linha — a 1ª é o limite no
  edge/reverse-proxy (Traefik), ver docs/infra-edge-hardening.md. Checa o header Content-Length
  (uploads multipart sempre o enviam); corpos sem Content-Length caem nos checks finos por endpoint.
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
_CSRF_COOKIE = "cria_csrf"
_CSRF_HEADER = b"x-csrf-token"
_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class SecurityMiddleware:
    def __init__(self, app, *, max_body_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        # M5: corte por Content-Length antes de qualquer leitura do corpo.
        for name, value in scope.get("headers") or []:
            if name == b"content-length":
                try:
                    if int(value) > self.max_body_bytes:
                        await self._too_large(send)
                        return
                except ValueError:
                    pass
                break

        # M8: acrescenta nosniff no início da resposta (funciona com bytes e streaming).
        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                if not any(k.lower() == b"x-content-type-options" for k, _ in headers):
                    headers.append((b"x-content-type-options", b"nosniff"))
            await send(message)

        await self.app(scope, receive, send_wrapper)

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

    Só age quando há o cookie de access (sessão por cookie) e o método muda estado: exige o header
    X-CSRF-Token igual ao cookie cria_csrf. O token CSRF só chega ao front pelo CORPO do login (a
    SOP impede lê-lo cross-site), então um POST forjado não casa o header.

    Passam direto: requisições só-Bearer (legado, sem cookie) e server-to-server como o webhook do
    Stripe (sem cookie); e os métodos seguros (GET/HEAD/OPTIONS).
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http" or scope.get("method") not in _UNSAFE_METHODS:
            await self.app(scope, receive, send)
            return

        headers = scope.get("headers") or []
        cookie_hdr = next((v for k, v in headers if k == b"cookie"), b"")
        cookies = SimpleCookie()
        cookies.load(cookie_hdr.decode("latin-1"))

        if _ACCESS_COOKIE not in cookies:  # não é sessão por cookie → CSRF não se aplica
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
