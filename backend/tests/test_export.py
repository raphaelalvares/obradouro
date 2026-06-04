"""Testes do empacotamento de export (Fase 8) — puros, sem DB/storage."""

import io
import zipfile

from app.services.export_pacote import csv_checklist, csv_estoque, montar_zip, slug


def test_slug():
    assert slug("Reforma Apto 302") == "reforma-apto-302"
    assert slug("Café é ótimo!") == "cafe-e-otimo"
    assert slug("   ") == "obra"
    assert slug(None) == "obra"


def test_csv_checklist_cabecalho_e_numero_br():
    linhas = [
        {
            "etapa_seq": 1,
            "etapa": "Alvenaria",
            "nivel": "tarefa",
            "item": "Parede da sala",
            "estado": "pendente",
            "ambiente": "Sala",
            "unidade": "m2",
            "quantidade": 12.5,
            "custo_total": 1000,
            "concluido_por": None,
            "concluido_em": None,
        }
    ]
    s = csv_checklist(linhas)
    assert "Etapa #;Etapa;Nível" in s  # separador ';'
    assert "Alvenaria" in s
    assert "12,5" in s  # vírgula decimal
    assert "1000" in s


def test_csv_estoque():
    linhas = [
        {
            "nf": "6170",
            "fornecedor": "Posto X",
            "data_chegada": None,
            "item": "Óleo diesel",
            "unidade": "L",
            "quantidade_nota": 300,
            "quantidade_conferida": 298.5,
            "valor_unitario": 5.123,
            "valor_total": 1500,
        }
    ]
    s = csv_estoque(linhas)
    assert "NF-e;Fornecedor" in s
    assert "Posto X" in s
    assert "298,5" in s


def test_montar_zip_estrutura_em_camadas():
    obras = [
        {"pasta": "obra-1-reforma", "checklist_csv": "a;b\n", "estoque_csv": "c;d\n"},
        {"pasta": "obra-2-casa", "checklist_csv": "x;y\n", "estoque_csv": "z;w\n"},
    ]
    fotos = [("obra-1-reforma/fotos/1-foto.jpg", b"\xff\xd8\xff-bytes-jpeg")]
    out = montar_zip(obras, fotos, "01/01/2026 10:00")

    z = zipfile.ZipFile(io.BytesIO(out))
    nomes = set(z.namelist())
    assert "leia-me.txt" in nomes
    assert "obra-1-reforma/checklist.csv" in nomes
    assert "obra-1-reforma/estoque.csv" in nomes
    assert "obra-2-casa/checklist.csv" in nomes
    assert "obra-1-reforma/fotos/1-foto.jpg" in nomes
    assert z.read("obra-1-reforma/fotos/1-foto.jpg") == b"\xff\xd8\xff-bytes-jpeg"
    # CSV gravado com BOM utf-8 (Excel pt-BR)
    assert z.read("obra-1-reforma/checklist.csv").startswith(b"\xef\xbb\xbf")
    assert "Obras neste pacote (2)" in z.read("leia-me.txt").decode("utf-8")
