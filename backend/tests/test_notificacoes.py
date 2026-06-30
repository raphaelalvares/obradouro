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


def test_link_portal_cadastro_codifica_email():
    # o e-mail vai no querystring (?email=) e tem de ser percent-encoded (@ → %40).
    link = notificacoes._link_portal_cadastro("cliente+tag@email.com")
    assert "/portal/cadastro?email=" in link
    assert "%40email.com" in link
    assert "@email.com" not in link


async def test_notificar_convite_cliente_compoe_sem_quebrar():
    # compõe o convite (projeto e obra) e cai no no-op do enviar_email (sem Resend no teste).
    await notificacoes.notificar_convite_cliente(
        cliente_email="cliente@email.com", arquiteto_nome="Ana", alvo_nome="Casa 302",
        alvo_tipo="projeto",
    )
    await notificacoes.notificar_convite_cliente(
        cliente_email="cliente@email.com", arquiteto_nome=None, alvo_nome=None, alvo_tipo="obra",
    )


async def test_notificar_convite_sem_email_nao_quebra():
    # sem e-mail do cliente → retorna cedo, sem exceção.
    await notificacoes.notificar_convite_cliente(
        cliente_email="", arquiteto_nome="Ana", alvo_nome="X", alvo_tipo="projeto",
    )
