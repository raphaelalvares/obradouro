"""Renderização do PDF da PROPOSTA COMERCIAL do orçamento (documento para o CLIENTE).

Função PURA (sem DB/IO): recebe a proposta já montada (visão de VENDA — _proposta_etapas) e devolve
os bytes. Identidade visual espelha o PDF do checklist (pdf_render): fpdf2 com fontes core
(Helvetica/latin-1), paleta âmbar, logo + nome do escritório no cabeçalho e rodapé em toda página.
NUNCA recebe custos crus nem percentuais (majoração/BDI/imposto) — só preços de venda.
"""

import io

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from app.services.pdf_render import _AMBER, _DARK, _GRAY, _MID, _lat1, _num

_LIGHT = (245, 240, 230)  # fundo suave (faixa do total)


def _brl(v) -> str:
    """R$ no formato BR (1.234,56). Sem locale: troca de separadores sobre o f-string en-US."""
    f = float(v or 0)
    s = f"{f:,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    return f"R$ {s}"


def _data_br(d) -> str:
    return d.strftime("%d/%m/%Y") if d else "-"


class _PropostaPDF(FPDF):
    """Cabeçalho compacto nas páginas 2+ e rodapé com escritório/página em todas."""

    titulo_corrente = ""
    rodape_esquerda = ""
    rodape_direita = ""

    def header(self) -> None:
        if self.page_no() == 1:
            return  # a 1ª página tem o cabeçalho rico (logo/título), desenhado no corpo
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*_GRAY)
        self.cell(0, 6, _lat1(self.titulo_corrente), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*_AMBER)
        self.set_line_width(0.3)
        y = self.get_y() + 1
        self.line(self.l_margin, y, self.l_margin + self.epw, y)
        self.ln(4)

    def footer(self) -> None:
        self.set_y(-13)
        self.set_draw_color(*_AMBER)
        self.set_line_width(0.3)
        self.line(self.l_margin, self.get_y(), self.l_margin + self.epw, self.get_y())
        self.set_y(-11)
        self.set_font("Helvetica", size=8)
        self.set_text_color(*_GRAY)
        self.cell(self.epw / 3, 8, _lat1(self.rodape_esquerda), align="L")
        self.cell(self.epw / 3, 8, f"Página {self.page_no()}/{{nb}}", align="C")
        self.cell(self.epw / 3, 8, _lat1(self.rodape_direita), align="R")


def _quebra_se_precisa(pdf: _PropostaPDF, altura: float) -> None:
    if pdf.will_page_break(altura):
        pdf.add_page()


def _linha_valor(
    pdf: _PropostaPDF, texto: str, valor: str, *, indent: float = 0.0, alto: float = 5.5,
    bold: bool = False, cor=None,
) -> None:
    """Linha 'texto à esquerda, valor à direita' com descrição multi-linha sem rasgar o valor."""
    epw = pdf.epw
    w_txt = epw - indent - 32
    pdf.set_font("Helvetica", "B" if bold else "", 10 if bold else 9.5)
    linhas = pdf.multi_cell(w_txt, alto, _lat1(texto), dry_run=True, output="LINES")
    _quebra_se_precisa(pdf, alto * max(len(linhas), 1) + 1)
    pdf.set_text_color(*(cor or (_DARK if bold else _MID)))
    y0 = pdf.get_y()
    pdf.set_x(pdf.l_margin + indent)
    pdf.multi_cell(w_txt, alto, _lat1(texto), align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    y1 = pdf.get_y()
    pdf.set_xy(pdf.l_margin + epw - 32, y0)
    pdf.set_text_color(*(cor or _DARK))
    pdf.cell(32, alto, _lat1(valor), align="R")
    pdf.set_y(y1)


def render_orcamento_pdf(
    proposta: dict,
    nome_escritorio: str | None,
    logo_bytes: bytes | None,
    gerado_em: str,
) -> bytes:
    """Monta o PDF da proposta. `proposta` = saída de get_proposta (etapas com preço de VENDA)."""
    pdf = _PropostaPDF(orientation="P", unit="mm", format="A4")
    projeto = proposta.get("projeto_nome") or "Projeto"
    pdf.titulo_corrente = f"Proposta comercial - {projeto}"
    pdf.rodape_esquerda = nome_escritorio or ""
    pdf.rodape_direita = f"gerado em {gerado_em}"
    pdf.set_auto_page_break(True, margin=18)
    pdf.set_margins(15, 14, 15)
    pdf.add_page()
    epw = pdf.epw

    # ---------- cabeçalho rico (página 1): logo + escritório + título ----------
    top = pdf.get_y()
    if logo_bytes:
        try:
            from PIL import Image

            img = Image.open(io.BytesIO(logo_bytes))
            ratio = (img.width / img.height) if img.height else 1.0
            max_w, max_h = 50.0, 18.0
            w = max_w
            h = w / ratio
            if h > max_h:
                h, w = max_h, max_h * ratio
            pdf.image(img, x=pdf.l_margin, y=top, w=w, h=h)
            pdf.set_y(top + h + 3)
        except Exception:  # noqa: BLE001 (logo é decorativo: nunca derruba o PDF)
            pass

    if nome_escritorio:
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(*_DARK)
        pdf.cell(0, 6, _lat1(nome_escritorio), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*_AMBER)
    pdf.cell(0, 5, "PROPOSTA COMERCIAL", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "B", 17)
    pdf.set_text_color(*_DARK)
    pdf.multi_cell(epw, 8.5, _lat1(projeto), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("Helvetica", size=9)
    pdf.set_text_color(*_GRAY)
    meta = f"Revisão R{proposta.get('numero', 0)}"
    if proposta.get("data"):
        meta += f"  -  Data: {_data_br(proposta['data'])}"
    if proposta.get("validade"):
        meta += f"  -  Válida até: {_data_br(proposta['validade'])}"
    pdf.cell(0, 5, _lat1(meta), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.ln(2)
    pdf.set_draw_color(*_AMBER)
    pdf.set_line_width(0.6)
    y = pdf.get_y()
    pdf.line(pdf.l_margin, y, pdf.l_margin + epw, y)
    pdf.ln(5)

    # ---------- corpo: etapas → linhas com preço de venda ----------
    etapas = proposta.get("etapas") or []
    if not etapas:
        pdf.set_font("Helvetica", "I", 11)
        pdf.set_text_color(*_GRAY)
        pdf.cell(0, 8, _lat1("Proposta sem itens."), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    for g in etapas:
        _quebra_se_precisa(pdf, 16)  # não deixa o título da etapa órfão no pé da página
        _linha_valor(
            pdf, (g.get("etapa") or "").upper(), _brl(g.get("valor")), alto=6.5, bold=True
        )
        ylin = pdf.get_y() + 0.5
        pdf.set_draw_color(*_GRAY)
        pdf.set_line_width(0.2)
        pdf.line(pdf.l_margin, ylin, pdf.l_margin + epw, ylin)
        pdf.ln(2)
        for it in g.get("itens") or []:
            texto = it.get("descricao") or ""
            detalhes = []
            if it.get("ambiente"):
                detalhes.append(str(it["ambiente"]))
            if it.get("quantidade") is not None:
                detalhes.append(f"{_num(it['quantidade'])} {it.get('unidade') or 'un'}".strip())
            elif it.get("unidade"):
                detalhes.append(str(it["unidade"]))
            if detalhes:
                texto += f"  ({' - '.join(detalhes)})"
            _linha_valor(pdf, texto, _brl(it.get("valor")), indent=2)
        pdf.ln(4)

    # ---------- total ----------
    _quebra_se_precisa(pdf, 18)
    pdf.set_fill_color(*_LIGHT)
    pdf.set_draw_color(*_AMBER)
    pdf.set_line_width(0.4)
    y0 = pdf.get_y()
    pdf.rect(pdf.l_margin, y0, epw, 13, style="FD")
    pdf.set_y(y0 + 3.5)
    pdf.set_x(pdf.l_margin + 4)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*_MID)
    pdf.cell(epw / 2, 6, _lat1("VALOR TOTAL DA PROPOSTA"))
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(*_DARK)
    pdf.set_xy(pdf.l_margin + epw / 2 - 4, y0 + 3.5)
    pdf.cell(epw / 2, 6, _lat1(_brl(proposta.get("preco_final"))), align="R")
    pdf.set_y(y0 + 16)

    # ---------- condições / observações ----------
    obs = (proposta.get("observacoes") or "").strip()
    if obs:
        _quebra_se_precisa(pdf, 16)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*_AMBER)
        pdf.cell(0, 6, _lat1("CONDIÇÕES E OBSERVAÇÕES"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", size=9.5)
        pdf.set_text_color(*_MID)
        pdf.multi_cell(epw, 5, _lat1(obs), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(2)

    if proposta.get("validade"):
        pdf.set_font("Helvetica", "I", 8.5)
        pdf.set_text_color(*_GRAY)
        pdf.cell(
            0, 5, _lat1(f"Proposta válida até {_data_br(proposta['validade'])}."),
            new_x=XPos.LMARGIN, new_y=YPos.NEXT,
        )

    return bytes(pdf.output())
