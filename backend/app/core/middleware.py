"""Middleware de segurança (ASGI puro — robusto inclusive com respostas em streaming).

- M5: rejeita o corpo da requisição que excede o teto, ANTES de a aplicação lê-lo (defesa-em-
  profundidade contra DoS de memória/disco por upload gigante). É a 2ª linha — a 1ª é o limite no
  edge/reverse-proxy (Traefik), ver docs/infra-edge-hardening.md. Checa o header Content-Length
  (uploads multipart sempre o enviam); corpos sem Content-Length caem nos checks finos por endpoint.
- M8: injeta `X-Content-Type-Options: nosniff` em TODA resposta (cobre a mídia servida pela API —
  evita content-sniffing de um anexo malicioso). Idempotente (não duplica se já houver).
"""

from collections.abc import Awaitable, Callable

Scope = dict
Message = dict
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]


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
