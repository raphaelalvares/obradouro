"""SecurityMiddleware (M5/M8): corta corpo grande (413) e injeta nosniff em toda resposta."""

from app.core.middleware import SecurityMiddleware


async def _inner(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


async def _run(mw, headers):
    sent: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg):
        sent.append(msg)

    await mw({"type": "http", "headers": headers}, receive, send)
    return sent


async def test_rejeita_corpo_acima_do_teto_413():
    mw = SecurityMiddleware(_inner, max_body_bytes=100)
    sent = await _run(mw, [(b"content-length", b"999")])
    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 413


async def test_corpo_dentro_do_teto_passa_e_ganha_nosniff():
    mw = SecurityMiddleware(_inner, max_body_bytes=100)
    sent = await _run(mw, [(b"content-length", b"2")])
    start = next(m for m in sent if m["type"] == "http.response.start")
    assert start["status"] == 200
    assert (b"x-content-type-options", b"nosniff") in start["headers"]


async def test_sem_content_length_passa_com_nosniff():
    mw = SecurityMiddleware(_inner, max_body_bytes=100)
    sent = await _run(mw, [])
    start = next(m for m in sent if m["type"] == "http.response.start")
    assert start["status"] == 200
    assert (b"x-content-type-options", b"nosniff") in start["headers"]


# ---- M5 fino: corpo chunked / sem Content-Length confiável (conta os bytes ao ler) ----
async def _drena(scope, receive, send):
    """App que LÊ o corpo inteiro ANTES de responder (como o parsing de request do FastAPI)."""
    while True:
        msg = await receive()
        if not msg.get("more_body"):
            break
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


async def _run_stream(mw, chunks):
    sent: list[dict] = []
    it = iter(chunks)

    async def receive():
        try:
            return {"type": "http.request", "body": next(it), "more_body": True}
        except StopIteration:
            return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg):
        sent.append(msg)

    await mw({"type": "http", "headers": []}, receive, send)
    return sent


async def test_rejeita_corpo_chunked_acima_do_teto_413():
    # sem Content-Length: o teto vale CONTANDO os bytes lidos (60+60 > 100) → 413 antes da resposta.
    mw = SecurityMiddleware(_drena, max_body_bytes=100)
    sent = await _run_stream(mw, [b"x" * 60, b"y" * 60])
    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 413


async def test_corpo_chunked_dentro_do_teto_passa():
    mw = SecurityMiddleware(_drena, max_body_bytes=100)
    sent = await _run_stream(mw, [b"x" * 30, b"y" * 30])
    start = next(m for m in sent if m["type"] == "http.response.start")
    assert start["status"] == 200
    assert (b"x-content-type-options", b"nosniff") in start["headers"]
