"""Notificações ao arquiteto — e-mail transacional via Resend (API HTTP).

BEST-EFFORT: nunca quebra o fluxo de negócio. Se o Resend não está configurado (sem RESEND_API_KEY/
RESEND_FROM) ou a chamada falha, loga e segue — a fonte GARANTIDA do aviso é o registro no app
(histórico do projeto + funil, gravados na transação); o e-mail é reforço.

Disparado em BackgroundTask do FastAPI (após a resposta). NOTA: no FastAPI o teardown da dependência
de sessão (o commit) roda DEPOIS da BackgroundTask — i.e., o e-mail sai um instante antes do commit
final. Como é best-effort e o commit dessa transação praticamente nunca falha (o RPC já executou), o
pior caso é uma notificação espúria por um rollback raro — mesmo risco de qualquer endpoint de
escrita do app. Por isso a decisão/auditoria (na transação) é a fonte de verdade.
"""

import datetime as dt
import html
import logging
from urllib.parse import quote

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_RODAPE = "Obra D'Ouro — gestão de obra"

_RESEND_URL = "https://api.resend.com/emails"
_TIMEOUT = httpx.Timeout(10.0)

# decisão → (verbo no assunto, rótulo no corpo)
_DECISAO_LABEL = {
    "aprovado": "aprovou",
    "recusado": "recusou",
    "alteracao_pedida": "pediu alteração em",
}


async def enviar_email(*, to: str, subject: str, html: str, text: str | None = None) -> bool:
    """Envia um e-mail pelo Resend. Retorna True se enviou; False (sem levantar) se no-op/falha."""
    settings = get_settings()
    if not settings.email_configurado:
        logger.info("e-mail não enviado (Resend não configurado): %s", subject)
        return False
    payload: dict = {"from": settings.RESEND_FROM, "to": [to], "subject": subject, "html": html}
    if text:
        payload["text"] = text
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                _RESEND_URL,
                json=payload,
                headers={
                    "Authorization": f"Bearer {settings.RESEND_API_KEY.get_secret_value()}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
        return True
    except Exception:  # noqa: BLE001 — best-effort: nunca propaga p/ não derrubar a BackgroundTask
        logger.exception("falha ao enviar e-mail via Resend: %s", subject)
        return False


def _link_proposta(projeto_id: str) -> str:
    base = get_settings().app_base_url
    return f"{base}/projetos/{projeto_id}/orcamento"


def _link_portal_cadastro(email: str) -> str:
    """Link público de cadastro do portal, com o e-mail autorizado pré-preenchido (poka-yoke: o
    cliente se cadastra com o MESMO e-mail que casa a pré-autorização)."""
    base = get_settings().app_base_url
    return f"{base}/portal/cadastro?email={quote(email)}"


async def notificar_convite_cliente(
    *,
    cliente_email: str,
    arquiteto_nome: str | None,
    alvo_nome: str | None,
    alvo_tipo: str,  # 'projeto' | 'obra'
) -> None:
    """Convida o cliente ao portal: e-mail com o link de cadastro. Best-effort (Resend).

    Disparado em BackgroundTask ao autorizar o acesso (ou no 'Reenviar'). O convite NÃO é fronteira
    de segurança — o cadastro segue exigindo o e-mail confirmado (Supabase) + a pré-autorização do
    arquiteto. Sem Resend configurado vira no-op (o arquiteto ainda pode copiar o link)."""
    if not cliente_email:
        return
    quem = arquiteto_nome or "Seu arquiteto"
    quem_h = html.escape(quem)
    artigo = "o projeto" if alvo_tipo == "projeto" else "a obra"
    padrao = "seu projeto" if alvo_tipo == "projeto" else "sua obra"
    alvo_h = html.escape(alvo_nome) if alvo_nome else padrao
    link = _link_portal_cadastro(cliente_email)
    email_h = html.escape(cliente_email)
    subject = f"Seu acesso ao portal — {alvo_nome}" if alvo_nome else "Seu acesso ao portal"
    corpo = (
        f"<div style='font-family:Arial,Helvetica,sans-serif;color:#212121;max-width:520px'>"
        f"<p>Olá!</p>"
        f"<p><strong>{quem_h}</strong> liberou seu acesso ao portal para você acompanhar "
        f"{artigo} <strong>{alvo_h}</strong>.</p>"
        f"<p>Crie seu acesso com este e-mail: <strong>{email_h}</strong> "
        f"(escolha uma senha sua).</p>"
        f"<p style='margin-top:24px'>"
        f"<a href='{link}' style='background:#d4af37;color:#fff;text-decoration:none;"
        f"padding:10px 20px;border-radius:8px;display:inline-block'>Criar meu acesso</a></p>"
        f"<p style='color:#6e6e6e;font-size:12px;margin-top:8px'>Se o botão não funcionar, "
        f"copie e cole no navegador:<br>{link}</p>"
        f"<p style='color:#6e6e6e;font-size:12px;margin-top:24px'>Obra D'Ouro — gestão de obra</p>"
        f"</div>"
    )
    texto = (
        f"Olá!\n\n{quem} liberou seu acesso ao portal para acompanhar {artigo} "
        f"{alvo_nome or padrao}."
        f"\n\nCrie seu acesso com este e-mail: {cliente_email} (escolha uma senha sua)."
        f"\n\nLink de cadastro: {link}\n\nObra D'Ouro — gestão de obra"
    )
    await enviar_email(to=cliente_email, subject=subject, html=corpo, text=texto)


async def notificar_proposta_decidida(
    *,
    arquiteto_email: str | None,
    arquiteto_nome: str | None,
    projeto_id: str,
    projeto_nome: str | None,
    numero: int,
    decisao: str,
    motivo: str | None,
    virou_ganho: bool,
) -> None:
    """Compõe e envia o e-mail de 'proposta decidida' ao arquiteto. Best-effort."""
    if not arquiteto_email:
        logger.info("sem e-mail do arquiteto p/ notificar a decisão do orçamento R%s", numero)
        return
    verbo = _DECISAO_LABEL.get(decisao, "decidiu")
    proj = projeto_nome or "seu projeto"
    subject = f"Proposta R{numero}: o cliente {verbo} — {proj}"
    # escapa o que vem do usuário antes de injetar no HTML (motivo é digitado pelo CLIENTE).
    proj_h = html.escape(proj)
    nome_h = html.escape(arquiteto_nome) if arquiteto_nome else None
    motivo_h = html.escape(motivo) if motivo else None
    saud = f"Olá, {nome_h}!" if nome_h else "Olá!"
    link = _link_proposta(projeto_id)
    motivo_html = (
        f"<p style='margin:16px 0;padding:12px 16px;background:#f5f0e6;border-radius:8px'>"
        f"<strong>Motivo:</strong> {motivo_h}</p>"
        if motivo_h
        else ""
    )
    ganho_html = (
        "<p style='color:#2e7d32'>A oportunidade foi movida para <strong>Ganho</strong> "
        "no funil.</p>"
        if virou_ganho
        else ""
    )
    corpo = (
        f"<div style='font-family:Arial,Helvetica,sans-serif;color:#212121;max-width:520px'>"
        f"<p>{saud}</p>"
        f"<p>O cliente <strong>{verbo}</strong> a proposta <strong>R{numero}</strong> "
        f"do projeto <strong>{proj_h}</strong>.</p>"
        f"{motivo_html}{ganho_html}"
        f"<p style='margin-top:24px'>"
        f"<a href='{link}' style='background:#d4af37;color:#fff;text-decoration:none;"
        f"padding:10px 20px;border-radius:8px;display:inline-block'>Abrir o orçamento</a></p>"
        f"<p style='color:#6e6e6e;font-size:12px;margin-top:24px'>Obra D'Ouro — gestão de obra</p>"
        f"</div>"
    )
    saud_txt = f"Olá, {arquiteto_nome}!" if arquiteto_nome else "Olá!"  # texto puro (sem escape)
    texto = (
        f"{saud_txt}\n\nO cliente {verbo} a proposta R{numero} do projeto {proj}."
        + (f"\nMotivo: {motivo}" if motivo else "")
        + ("\nA oportunidade foi movida para Ganho no funil." if virou_ganho else "")
        + f"\n\nAbra o orçamento: {link}\n\nObra D'Ouro — gestão de obra"
    )
    await enviar_email(to=arquiteto_email, subject=subject, html=corpo, text=texto)


# ===================== Billing (expiry / win-back / up-sell de GB) =====================
# Layout base compartilhado p/ não divergir da paleta Obra D'Ouro (#d4af37 no CTA, texto #212121,
# container 520px, fallback #6e6e6e, rodapé fixo). Todos best-effort via enviar_email.


def _link_config(qs: str = "") -> str:
    """Área de Configurações do arquiteto (Plano + Financeiro). qs opcional (ex.: '?winback=1')."""
    return f"{get_settings().app_base_url}/configuracoes{qs}"


def _saud(nome: str | None) -> tuple[str, str]:
    """(html, texto) da saudação — o nome do arquiteto vem do nosso banco (não do usuário), mas
    escapamos por higiene ao injetar no HTML."""
    if nome:
        return (f"Olá, {html.escape(nome)}!", f"Olá, {nome}!")
    return ("Olá!", "Olá!")


def _fmt_data(quando: dt.datetime | None) -> str:
    return quando.strftime("%d/%m/%Y") if quando else ""


def _brl(cents: int | None) -> str:
    if not cents:
        return ""
    return "R$ " + f"{cents / 100:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _cta(label: str, url: str) -> str:
    return (
        f"<p style='margin-top:24px'>"
        f"<a href='{url}' style='background:#d4af37;color:#fff;text-decoration:none;"
        f"padding:10px 20px;border-radius:8px;display:inline-block'>{html.escape(label)}</a></p>"
        f"<p style='color:#6e6e6e;font-size:12px;margin-top:8px'>Se o botão não funcionar, copie e "
        f"cole no navegador:<br>{html.escape(url)}</p>"
    )


def _wrap(inner: str) -> str:
    return (
        f"<div style='font-family:Arial,Helvetica,sans-serif;color:#212121;max-width:520px'>"
        f"{inner}"
        f"<p style='color:#6e6e6e;font-size:12px;margin-top:24px'>{_RODAPE}</p></div>"
    )


async def notificar_pagamento_falhou(*, to: str, nome: str | None, fatura_url: str | None) -> None:
    """Cartão recusado (dunning). CTA = pagar a fatura do Stripe (ou abrir o Financeiro)."""
    saud_h, saud_t = _saud(nome)
    url = fatura_url or _link_config()
    corpo = _wrap(
        f"<p>{saud_h}</p>"
        f"<p>Não conseguimos processar o pagamento da sua assinatura da <strong>Obra D'Ouro"
        f"</strong>. Seu acesso segue ativo por alguns dias, mas para não ser interrompido é "
        f"preciso regularizar a fatura.</p>"
        f"<p>Costuma ser cartão vencido ou sem limite — atualizar leva 1 minuto.</p>"
        + _cta("Regularizar pagamento", url)
    )
    texto = (
        f"{saud_t}\n\nNão conseguimos processar o pagamento da sua assinatura da Obra D'Ouro. Seu "
        f"acesso segue ativo por alguns dias; regularize para não ser interrompido.\n\n"
        f"Regularizar: {url}\n\n{_RODAPE}"
    )
    await enviar_email(
        to=to, subject="Pagamento recusado — regularize sua assinatura", html=corpo, text=texto
    )


async def notificar_cancelamento_agendado(
    *, to: str, nome: str | None, quando: dt.datetime | None
) -> None:
    """Cancelamento agendado p/ o fim do período — lembra que dá p/ reativar até lá."""
    saud_h, saud_t = _saud(nome)
    data = _fmt_data(quando)
    url = _link_config()
    corpo = _wrap(
        f"<p>{saud_h}</p>"
        f"<p>Sua assinatura da <strong>Obra D'Ouro</strong> está agendada para ser cancelada em "
        f"<strong>{data}</strong>. Até lá você mantém todo o acesso.</p>"
        f"<p>Mudou de ideia? Dá para reativar a qualquer momento antes dessa data.</p>"
        + _cta("Reativar assinatura", url)
    )
    texto = (
        f"{saud_t}\n\nSua assinatura da Obra D'Ouro será cancelada em {data}. Até lá o acesso "
        f"continua. Para reativar: {url}\n\n{_RODAPE}"
    )
    await enviar_email(
        to=to, subject="Sua assinatura será cancelada em breve", html=corpo, text=texto
    )


async def notificar_renovacao_proxima(
    *, to: str, nome: str | None, valor_cents: int | None, quando: dt.datetime | None
) -> None:
    """Aviso (opcional, gated) de que a assinatura renova em breve — só um heads-up."""
    saud_h, saud_t = _saud(nome)
    data = _fmt_data(quando)
    valor = _brl(valor_cents)
    quanto_h = f" de <strong>{valor}</strong>" if valor else ""
    quanto_t = f" de {valor}" if valor else ""
    url = _link_config()
    corpo = _wrap(
        f"<p>{saud_h}</p>"
        f"<p>Sua assinatura da <strong>Obra D'Ouro</strong> renova em <strong>{data}</strong>"
        f"{quanto_h}, no cartão em arquivo. Não precisa fazer nada — é só um aviso.</p>"
        f"<p>Quer trocar o cartão ou rever o plano? É por aqui.</p>"
        + _cta("Ver Financeiro", url)
    )
    texto = (
        f"{saud_t}\n\nSua assinatura da Obra D'Ouro renova em {data}{quanto_t}, no cartão em "
        f"arquivo. Gerenciar: {url}\n\n{_RODAPE}"
    )
    await enviar_email(to=to, subject=f"Sua assinatura renova em {data}", html=corpo, text=texto)


async def notificar_winback(*, to: str, nome: str | None, com_cupom: bool) -> None:
    """Re-sell/win-back: quem caiu p/ free. CTA leva ao re-checkout (com cupom, se elegível)."""
    saud_h, saud_t = _saud(nome)
    url = _link_config("?winback=1")
    cupom_h = (
        "<p>E para facilitar a volta, preparamos um <strong>desconto de retorno</strong> que já "
        "vem aplicado no seu checkout.</p>"
        if com_cupom
        else ""
    )
    cupom_t = " Preparamos um desconto de retorno já aplicado no checkout." if com_cupom else ""
    corpo = _wrap(
        f"<p>{saud_h}</p>"
        f"<p>Sentimos sua falta na <strong>Obra D'Ouro</strong>. Sua conta voltou ao plano "
        f"gratuito, então recursos como fotos ilimitadas, portal do cliente e mais espaço ficaram "
        f"indisponíveis — e suas obras continuam aqui, esperando por você.</p>"
        f"{cupom_h}" + _cta("Voltar a assinar", url)
    )
    texto = (
        f"{saud_t}\n\nSentimos sua falta na Obra D'Ouro. Sua conta voltou ao plano gratuito."
        f"{cupom_t}\n\nVoltar a assinar: {url}\n\n{_RODAPE}"
    )
    await enviar_email(to=to, subject="Que tal voltar para a Obra D'Ouro?", html=corpo, text=texto)


async def notificar_armazenamento_cheio(
    *, to: str, nome: str | None, pct: int, contratavel: bool
) -> None:
    """Up-sell de GB: espaço no limite. CTA leva ao contratar-GB (ou assinar, se free)."""
    saud_h, saud_t = _saud(nome)
    url = _link_config()
    acao_h = (
        "contrate mais espaço em segundos"
        if contratavel
        else "assine um plano para ampliar o espaço"
    )
    corpo = _wrap(
        f"<p>{saud_h}</p>"
        f"<p>Seu armazenamento na <strong>Obra D'Ouro</strong> está em <strong>{pct}%</strong>. "
        f"Quando lotar, novos envios de fotos e arquivos são bloqueados até liberar espaço.</p>"
        f"<p>Para não travar no meio de uma obra, {acao_h}.</p>"
        + _cta("Ampliar espaço", url)
    )
    texto = (
        f"{saud_t}\n\nSeu armazenamento na Obra D'Ouro está em {pct}%. Ao lotar, novos envios são "
        f"bloqueados. Amplie o espaço: {url}\n\n{_RODAPE}"
    )
    await enviar_email(
        to=to, subject=f"Seu espaço está em {pct}% — amplie antes de travar", html=corpo, text=texto
    )
