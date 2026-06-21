"""Renderização do PDF do checklist (Fase 7 — feature premium 'export_pdf').

Função PURA (sem DB/IO): recebe os dados já carregados e devolve os bytes do PDF. Isso a torna
trivial de testar (ver tests/test_pdf.py) e mantém a regra de plano/storage no service.

fpdf2 com fontes CORE (Helvetica): sem TTF embutida, peso mínimo e nenhuma dependência de sistema
(roda igual no Windows do dev e no container Linux). Core font usa latin-1 (WinAnsi), que cobre o
português; `_lat1` normaliza aspas/travessões unicode e troca o resto por '?' (em vez de estourar).
Checkbox em ASCII ([ ] [~] [x]) — também latin-1-safe e imprime bem em P&B.
"""

import io

from fpdf import FPDF
from fpdf.enums import XPos, YPos

_AMBER = (216, 165, 58)
_GRAY = (110, 110, 110)
_DARK = (33, 33, 33)
_MID = (70, 70, 70)

# Substituições antes do encode latin-1 (chars comuns que viriam de copiar/colar).
_REPL = {
    "—": "-", "–": "-", "‘": "'", "’": "'",
    "“": '"', "”": '"', "…": "...", " ": " ",
}

_BOX = {"concluido": "[x]", "em_andamento": "[~]", "pendente": "[ ]"}


def _lat1(s: str | None) -> str:
    if not s:
        return ""
    for k, v in _REPL.items():
        s = s.replace(k, v)
    return s.encode("latin-1", "replace").decode("latin-1")


def _num(n) -> str:
    """Número curto (BR): inteiro sem casas, senão até 3 casas com vírgula e sem zeros à direita."""
    try:
        f = float(n)
    except (TypeError, ValueError):
        return str(n)
    if f == int(f):
        return str(int(f))
    return f"{f:.3f}".rstrip("0").rstrip(".").replace(".", ",")


def _agrupar(itens: list[dict]) -> list[tuple[str | None, list[dict]]]:
    """Agrupa por `ambiente` preservando a ordem de 1ª aparição (espelha a tela do Cronograma)."""
    grupos: list[tuple[str | None, list[dict]]] = []
    idx: dict[str, int] = {}
    for it in itens:
        key = (it.get("ambiente") or "").strip()
        if key not in idx:
            idx[key] = len(grupos)
            grupos.append((key or None, []))
        grupos[idx[key]][1].append(it)
    return grupos


def _folhas(tarefa: dict) -> list[dict]:
    """Itens 'marcáveis' de uma tarefa: os sub-itens, ou a própria tarefa se não tiver sub-itens."""
    subs = tarefa.get("subitens") or []
    return subs if subs else [tarefa]


def _contagem_etapa(etapa: dict) -> tuple[int, int]:
    """feitos/total da etapa (espelha o front): folhas das tarefas (diretas + de subetapas) MAIS
    cada subetapa-marco (sem tarefas) como 1 unidade (feita se concluída)."""
    tarefas = list(etapa.get("itens") or [])
    for s in etapa.get("subetapas") or []:
        tarefas += s.get("itens") or []
    folhas = [lf for t in tarefas for lf in _folhas(t)]
    feitos = sum(1 for lf in folhas if lf.get("estado") == "concluido")
    total = len(folhas)
    for s in etapa.get("subetapas") or []:
        if not (s.get("itens") or []):
            total += 1
            if s.get("concluida"):
                feitos += 1
    return feitos, total


class _PDF(FPDF):
    def footer(self) -> None:  # roda em toda página
        self.set_y(-12)
        self.set_font("Helvetica", size=8)
        self.set_text_color(*_GRAY)
        self.cell(0, 8, f"Pagina {self.page_no()}/{{nb}}", align="C")


def _linha_item(pdf: _PDF, epw: float, item: dict, indent: float) -> None:
    estado = item.get("estado") or "pendente"
    box = _BOX.get(estado, "[ ]")
    nome = item.get("nome") or ""
    extra = ""
    q = item.get("quantidade")
    if q is not None:
        extra = f"  ({_num(q)} {item.get('unidade') or ''})".rstrip()
    pdf.set_font("Helvetica", size=10)
    pdf.set_text_color(*(_DARK if estado == "concluido" else _MID))
    pdf.set_x(pdf.l_margin + indent)
    pdf.multi_cell(
        epw - indent, 5.5, _lat1(f"{box} {nome}{extra}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT
    )
    por = item.get("concluido_por_nome")
    if estado == "concluido" and por:
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(*_GRAY)
        pdf.set_x(pdf.l_margin + indent + 6)
        pdf.multi_cell(
            epw - indent - 6, 4, _lat1(f"por {por}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT
        )


def _render_itens(pdf: _PDF, epw: float, itens: list[dict], base: float = 0.0) -> None:
    """Renderiza tarefas agrupadas por cômodo (tarefa-folha = 1 linha; tarefa com sub-itens = nome
    em negrito + sub-itens). `base` recua tudo (tarefas sob uma Subetapa ficam indentadas)."""
    grupos = _agrupar(itens)
    tem_amb = any(amb for amb, _ in grupos)
    for amb, gitens in grupos:
        if tem_amb:
            pdf.set_font("Helvetica", "B", 8)
            pdf.set_text_color(*_AMBER)
            pdf.set_x(pdf.l_margin + base)
            pdf.multi_cell(
                epw - base, 5, _lat1((amb or "Geral").upper()),
                new_x=XPos.LMARGIN, new_y=YPos.NEXT,
            )
        for tarefa in gitens:
            subs = tarefa.get("subitens") or []
            if subs:
                pdf.set_font("Helvetica", "B", 10)
                pdf.set_text_color(*_DARK)
                pdf.set_x(pdf.l_margin + base + 2)
                pdf.multi_cell(
                    epw - base - 2, 5.5, _lat1(tarefa.get("nome") or ""),
                    new_x=XPos.LMARGIN, new_y=YPos.NEXT,
                )
                for s in subs:
                    _linha_item(pdf, epw, s, indent=base + 8)
            else:
                _linha_item(pdf, epw, tarefa, indent=base + 2)
        pdf.ln(1)


def render_checklist_pdf(
    obra: dict,
    etapas: list[dict],
    nome_escritorio: str | None,
    logo_bytes: bytes | None,
    gerado_em: str,
) -> bytes:
    """Monta o PDF do checklist. `etapas` é a árvore de get_tree (etapa → tarefas → subitens)."""
    pdf = _PDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(True, margin=15)
    pdf.set_margins(15, 14, 15)
    pdf.add_page()
    epw = pdf.epw

    # ---------- cabeçalho (página 1) ----------
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

    pdf.set_font("Helvetica", "B", 17)
    pdf.set_text_color(*_DARK)
    pdf.cell(
        0, 9, _lat1(f"Cronograma - {obra.get('nome') or 'Obra'}"),
        new_x=XPos.LMARGIN, new_y=YPos.NEXT,
    )
    pdf.set_font("Helvetica", size=9)
    pdf.set_text_color(*_GRAY)
    seq = obra.get("seq_humano")
    sub = f"Obra #{seq}" if seq is not None else ""
    sub += (("  -  " if sub else "") + f"gerado em {gerado_em}")
    pdf.cell(0, 5, _lat1(sub), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.ln(2)
    pdf.set_draw_color(*_AMBER)
    pdf.set_line_width(0.6)
    y = pdf.get_y()
    pdf.line(pdf.l_margin, y, pdf.l_margin + epw, y)
    pdf.ln(4)

    if not etapas:
        pdf.set_font("Helvetica", "I", 11)
        pdf.set_text_color(*_GRAY)
        pdf.cell(0, 8, _lat1("Checklist vazio."), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        return bytes(pdf.output())

    # ---------- corpo ----------
    for etapa in etapas:
        feitos, total = _contagem_etapa(etapa)

        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(*_DARK)
        seqe = etapa.get("seq_humano")
        prefixo = f"#{seqe}  " if seqe is not None else ""
        pdf.multi_cell(
            epw, 7, _lat1(prefixo + (etapa.get("nome") or "")),
            new_x=XPos.LMARGIN, new_y=YPos.NEXT,
        )
        if total:
            pdf.set_font("Helvetica", size=8)
            pdf.set_text_color(*_GRAY)
            pdf.cell(
                0, 4, _lat1(f"{feitos}/{total} concluidos"),
                new_x=XPos.LMARGIN, new_y=YPos.NEXT,
            )
        pdf.ln(1.5)

        # subetapas primeiro (4º nível), depois as tarefas direto na etapa — igual à tela.
        for sub in etapa.get("subetapas") or []:
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_text_color(*_MID)
            seqs = sub.get("seq_humano")
            pre = f"#{seqs}  " if seqs is not None else ""
            pdf.set_x(pdf.l_margin + 1)
            pdf.multi_cell(
                epw - 1, 6, _lat1(pre + (sub.get("nome") or "")),
                new_x=XPos.LMARGIN, new_y=YPos.NEXT,
            )
            sub_itens = sub.get("itens") or []
            if sub_itens:
                _render_itens(pdf, epw, sub_itens, base=4)
            else:  # subetapa-marco (sem tarefas): linha com o estado de conclusão
                box = "[x]" if sub.get("concluida") else "[ ]"
                pdf.set_font("Helvetica", size=9)
                pdf.set_text_color(*_GRAY)
                pdf.set_x(pdf.l_margin + 6)
                pdf.multi_cell(
                    epw - 6, 5, _lat1(f"{box} (subetapa sem tarefas)"),
                    new_x=XPos.LMARGIN, new_y=YPos.NEXT,
                )
                pdf.ln(1)

        diretas = etapa.get("itens") or []
        if diretas:
            _render_itens(pdf, epw, diretas, base=0)
        if etapa.get("sem_itens"):  # etapa-marco (vazia): mostra o estado de conclusão
            box = "[x]" if etapa.get("concluida") else "[ ]"
            pdf.set_font("Helvetica", size=9)
            pdf.set_text_color(*_GRAY)
            pdf.set_x(pdf.l_margin + 2)
            pdf.multi_cell(
                epw - 2, 5, _lat1(f"{box} (etapa sem tarefas)"),
                new_x=XPos.LMARGIN, new_y=YPos.NEXT,
            )
        pdf.ln(2)

    return bytes(pdf.output())
