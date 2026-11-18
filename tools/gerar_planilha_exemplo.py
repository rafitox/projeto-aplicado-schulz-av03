"""Gera uma planilha de exemplo no formato Calypso/MMC.

A planilha serve para exercitar o upload do webapp **sem** usar os
arquivos da empresa: o layout reproduz o formato real (rótulos na linha N,
valores na N+1, cabeçalho da tabela na linha 13, dois blocos de medição),
com dados fictícios.

A construção usa apenas a biblioteca padrão — o arquivo é um ZIP com o
XML mínimo de um OOXML, igual ao que o leitor de reserva sabe interpretar.

Uso:
    python tools/gerar_planilha_exemplo.py
    python tools/gerar_planilha_exemplo.py --saida minha_planilha.xlsx
"""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

RAIZ = Path(__file__).resolve().parent.parent

#: Coluna -> (cabecalho, largura).
COLUNAS = [
    ("Characteristic", 24),
    ("Actual", 14),
    ("Nominal", 14),
    ("Upper Tol", 12),
    ("Lower Tol", 12),
    ("Deviation", 14),
]

#: Características do exemplo, com nominal, tolerâncias e dois valores medidos.
MEDICOES = [
    ("DIAMETRO_EXTERNO", "6.075", "0.01", "-0.01", "6.0787295", "6.0780314"),
    ("DIAMETRO_INTERNO", "16.964", "0.01", "-0.01", "16.9684482", "16.9698259"),
    ("POSICAO_X", "0", "0.1", "0", "0.4295522", "0.4295522"),
    ("POSICAO_Y", "0", "0.1", "0", "0.2446114", "0.2446114"),
    ("PLANICIDADE", "0", "0.05", "0", "0.002167", "0.002267"),
    ("RUGOSIDADE", "1.6", "0.2", "-0.2", "1.55", "1.56"),
]


def _coluna(letra: str) -> int:
    """Converte a letra da coluna em índice (A = 1)."""
    indice = 0
    for caractere in letra:
        indice = indice * 26 + (ord(caractere) - 64)
    return indice


def _referencia(linha: int, coluna: int) -> str:
    """Monta a referência de uma célula (``"B12"``)."""
    letras = ""
    indice = coluna
    while indice > 0:
        indice, resto = divmod(indice - 1, 26)
        letras = chr(65 + resto) + letras
    return f"{letras}{linha}"


def _celula(linha: int, coluna: int, valor: object, numerica: bool = False) -> str:
    """Gera o XML de uma célula."""
    referencia = _referencia(linha, coluna)
    if valor is None or valor == "":
        return f'<c r="{referencia}"/>'
    if numerica:
        return f'<c r="{referencia}"><v>{escape(str(valor))}</v></c>'
    return (
        f'<c r="{referencia}" t="inlineStr"><is><t>{escape(str(valor))}</t></is></c>'
    )


def _planilha_xml() -> str:
    """Monta o XML da aba ``Report`` com o layout Calypso/MMC."""
    linhas = []

    # Cabecalho do relatório (rótulos) e valores logo abaixo.
    rotulos = {
        2: {2: "Calypso Measuring Result"},
        4: {2: "Measurement Plan", 4: "Date", 6: "Order"},
        5: {2: "PLANO_EXEMPLO", 4: "2026-08-13"},
        7: {2: "Drawing No.", 4: "Time", 6: "Part No."},
        8: {2: "DESENHO_EXEMPLO", 4: "16:16:26", 6: "27"},
        10: {2: "Metrologista", 4: "MMC", 6: "Fornecedor"},
        11: {2: "José A. Rosa Jr", 4: "500008", 6: "CDM"},
    }
    for numero in sorted(rotulos):
        celulas = "".join(
            _celula(numero, coluna, valor)
            for coluna, valor in sorted(rotulos[numero].items())
        )
        linhas.append(f'<row r="{numero}">{celulas}</row>')

    # Cabeçalho da tabela de medições (linha 13).
    cabecalho = "".join(
        _celula(13, indice, nome) for indice, (nome, _) in enumerate(COLUNAS, start=1)
    )
    linhas.append(f'<row r="13">{cabecalho}</row>')

    # Primeiro bloco: linhas 14 a 19, com a primeira medida.
    numero = 14
    for caracteristica, nominal, tol_sup, tol_inf, medida_1, _ in MEDICOES:
        valores = [caracteristica, medida_1, nominal, tol_sup, tol_inf]
        celulas = "".join(
            _celula(numero, indice, valor, numerica=indice > 1)
            for indice, valor in enumerate(valores, start=1)
        )
        linhas.append(f'<row r="{numero}">{celulas}</row>')
        numero += 1

    # Linha 20 em branco: separa os dois blocos.
    linhas.append('<row r="20"/>')

    # Segundo bloco: linhas 21 a 26, com a segunda medida.
    numero = 21
    for caracteristica, nominal, tol_sup, tol_inf, _, medida_2 in MEDICOES:
        valores = [caracteristica, medida_2, nominal, tol_sup, tol_inf]
        celulas = "".join(
            _celula(numero, indice, valor, numerica=indice > 1)
            for indice, valor in enumerate(valores, start=1)
        )
        linhas.append(f'<row r="{numero}">{celulas}</row>')
        numero += 1

    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(linhas)}</sheetData></worksheet>'
    )


def gerar(destino: Path) -> Path:
    """Grava a planilha de exemplo no caminho indicado."""
    workbook = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
        ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Report" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/></Relationships>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '</Types>'
    )
    raiz_rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Target="xl/workbook.xml"'
        ' Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"/>'
        '</Relationships>'
    )

    destino.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as pacote:
        pacote.writestr("[Content_Types].xml", content_types)
        pacote.writestr("_rels/.rels", raiz_rels)
        pacote.writestr("xl/workbook.xml", workbook)
        pacote.writestr("xl/_rels/workbook.xml.rels", rels)
        pacote.writestr("xl/worksheets/sheet1.xml", _planilha_xml())
    return destino


def main() -> int:
    """Gera a planilha de exemplo."""
    analisador = argparse.ArgumentParser(
        description="Gera uma planilha de exemplo no formato Calypso/MMC"
    )
    analisador.add_argument(
        "--saida",
        default=str(RAIZ / "planilha_exemplo.xlsx"),
        help="Caminho do arquivo .xlsx a gerar",
    )
    argumentos = analisador.parse_args()

    destino = gerar(Path(argumentos.saida))
    print(f"Planilha de exemplo gerada: {destino}")

    # Verifica de imediato que o ETL do projeto consegue lê-la.
    import sys

    sys.path.insert(0, str(RAIZ))
    from schulz_mvp.etl import processar_planilha

    resultado = processar_planilha(destino)
    print(f"  Leitura verificada: {resultado.total_registros} medicoes, "
          f"{len(resultado.blocos)} bloco(s), {resultado.total_pendencias} pendencia(s)")
    print(f"  Plano: {resultado.metadados.get('plano_medicao')}")
    print(f"  Metrologista: {resultado.metadados.get('metrologista')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
