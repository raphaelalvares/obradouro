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

import html
import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

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
        f"<a href='{link}' style='background:#d8a53a;color:#fff;text-decoration:none;"
        f"padding:10px 20px;border-radius:8px;display:inline-block'>Abrir o orçamento</a></p>"
        f"<p style='color:#6e6e6e;font-size:12px;margin-top:24px'>CRIA — gestão de obra</p>"
        f"</div>"
    )
    saud_txt = f"Olá, {arquiteto_nome}!" if arquiteto_nome else "Olá!"  # texto puro (sem escape)
    texto = (
        f"{saud_txt}\n\nO cliente {verbo} a proposta R{numero} do projeto {proj}."
        + (f"\nMotivo: {motivo}" if motivo else "")
        + ("\nA oportunidade foi movida para Ganho no funil." if virou_ganho else "")
        + f"\n\nAbra o orçamento: {link}\n\nCRIA — gestão de obra"
    )
    await enviar_email(to=arquiteto_email, subject=subject, html=corpo, text=texto)
