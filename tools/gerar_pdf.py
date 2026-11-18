"""Gera o PDF do documento técnico a partir do Markdown.

O pipeline principal usa o LaTeX:

1. ``pandoc`` converte o Markdown em LaTeX e chama o ``pdflatex``;
2. margens de 1,5 cm e corpo de 9pt dão espaço às tabelas de 4 colunas.

O LaTeX foi escolhido depois de comparar as duas rotas: o LibreOffice
(``pandoc`` -> ODT -> ``soffice``) funciona, mas quebra os nomes longos de
método **no meio da palavra** (``medicao.id_tecnico`` virava
``medicao.id_te|cnico``), porque o ODF não tem pontos de quebra dentro de
um trecho de código. O ``longtable`` do LaTeX prefere deixar o trecho
inteiro, mesmo que ele encoste na borda da coluna.

O LaTeX exige dois ajustes no Markdown:

* os caracteres de moldura Unicode (``├``, ``│``, ``─``) viram ASCII — o
  ``pdflatex`` não os aceita;
* o sinal de menos Unicode (U+2212) vira hífen.

Como o PDF é gerado a partir do Markdown, e o Markdown é a fonte da
verdade, a conversão é feita numa cópia temporária — o arquivo do projeto
permanece legível.

Uso:
    python tools/gerar_pdf.py
    python tools/gerar_pdf.py --markdown 06_mvp_parte1.md --saida 06_mvp_parte1.pdf
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

#: Caracteres de moldura Unicode -> ASCII equivalente.
MOLDURA_UNICODE = {
    "┌": "+", "┐": "+", "└": "+", "┘": "+",
    "├": "+", "┤": "+", "┬": "+", "┴": "+", "┼": "+",
    "─": "-", "│": "|", "━": "-", "┃": "|",
    "╭": "+", "╮": "+", "╰": "+", "╯": "+",
    "╔": "+", "╗": "+", "╚": "+", "╝": "+",
    "║": "|", "═": "=",
}

#: Opcoes de paginacao aplicadas ao LaTeX.
PAGINACAO = [
    "-V", "geometry:margin=1.5cm",
    "-V", "fontsize=9pt",
]


def preparar_markdown(origem: Path, destino: Path) -> None:
    """Cria uma copia do Markdown com os caracteres aceitos pelo LaTeX."""
    texto = origem.read_text(encoding="utf-8")
    for unicode_char, ascii_char in MOLDURA_UNICODE.items():
        texto = texto.replace(unicode_char, ascii_char)
    # O sinal de menos Unicode nao e aceito pelo pdflatex em texto.
    texto = texto.replace("\u2212", "-")
    destino.write_text(texto, encoding="utf-8")


def gerar_com_latex(markdown: Path, saida: Path) -> bool:
    """Gera o PDF com pdflatex. Devolve False se a ferramenta faltar."""
    if shutil.which("pandoc") is None or shutil.which("pdflatex") is None:
        return False
    comando = [
        "pandoc", str(markdown),
        "-o", str(saida),
        "--pdf-engine=pdflatex",
        *PAGINACAO,
    ]
    resultado = subprocess.run(comando, capture_output=True, text=True)
    if resultado.returncode != 0:
        print("AVISO: o pdflatex falhou; usando a rota alternativa.",
              file=sys.stderr)
        print(resultado.stderr[:800], file=sys.stderr)
        return False
    return saida.exists()


def gerar_com_libreoffice(markdown: Path, saida: Path) -> bool:
    """Gera o PDF via ODT e LibreOffice — rota alternativa."""
    if not all(shutil.which(ferramenta) for ferramenta in ("pandoc", "soffice")):
        return False
    with tempfile.TemporaryDirectory(prefix="schulz_pdf_") as temporario:
        temporario = Path(temporario)
        odt = temporario / (markdown.stem + ".odt")
        subprocess.run(["pandoc", str(markdown), "-o", str(odt)], check=True)
        subprocess.run(
            ["soffice", "--headless", "--norestore", "--convert-to", "pdf",
             "--outdir", str(temporario), str(odt)],
            check=True, capture_output=True,
        )
        gerado = odt.with_suffix(".pdf")
        if not gerado.exists():
            return False
        shutil.copy(gerado, saida)
    return True


def main() -> int:
    """Executa o pipeline de geração do PDF."""
    analisador = argparse.ArgumentParser(description="Gera o PDF do documento técnico")
    analisador.add_argument(
        "--markdown", default=str(RAIZ / "06_mvp_parte1.md"), help="Arquivo Markdown"
    )
    analisador.add_argument(
        "--saida", default=str(RAIZ / "06_mvp_parte1.pdf"), help="PDF de saída"
    )
    argumentos = analisador.parse_args()

    markdown = Path(argumentos.markdown)
    saida = Path(argumentos.saida)
    if not markdown.exists():
        print(f"ERRO: arquivo não encontrado: {markdown}", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory(prefix="schulz_build_") as temporario:
        preparado = Path(temporario) / markdown.name
        preparar_markdown(markdown, preparado)

        pdf_temporario = Path(temporario) / saida.name
        print("[1/2] pandoc + pdflatex")
        if not gerar_com_latex(preparado, pdf_temporario):
            print("[2/2] pandoc + LibreOffice (rota alternativa)")
            if not gerar_com_libreoffice(preparado, pdf_temporario):
                print("ERRO: nenhuma das rotas de geração funcionou.", file=sys.stderr)
                return 1
        else:
            print("[2/2] concluído")

        shutil.copy(pdf_temporario, saida)

    print(f"\nPDF gerado: {saida} ({saida.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
