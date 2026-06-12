"""Testes da notificação por e-mail (Resend) — sem rede: o no-op quando não configurado."""

from app.services import notificacoes


async def test_enviar_email_noop_sem_config():
    # sem RESEND_API_KEY/RESEND_FROM no ambiente de teste → no-op, retorna False, não levanta.
    ok = await notificacoes.enviar_email(to="a@b.com", subject="x", html="<p>x</p>")
    assert ok is False


async def test_notificar_sem_email_do_arquiteto_nao_quebra():
    # arquiteto sem e-mail → apenas loga e retorna (best-effort), sem exceção.
    await notificacoes.notificar_proposta_decidida(
        arquiteto_email=None, arquiteto_nome=None, projeto_id="p", projeto_nome="Proj",
        numero=1, decisao="aprovado", motivo=None, virou_ganho=True,
    )


async def test_notificar_compoe_sem_quebrar():
    # com e-mail mas sem Resend configurado: compõe o corpo e cai no no-op do enviar_email.
    await notificacoes.notificar_proposta_decidida(
        arquiteto_email="arq@x.com", arquiteto_nome="Ana", projeto_id="p1", projeto_nome="Casa",
        numero=2, decisao="alteracao_pedida", motivo="trocar piso", virou_ganho=False,
    )
