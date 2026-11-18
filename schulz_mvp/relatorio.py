"""Renderização do relatório de calibração no terminal.

O relatório usa moldura ASCII (````+```` e ``-``) em vez de caracteres de
moldura Unicode (``┌``, ``│``, ``─``). O pipeline de conversão do relatório
para PDF passa por LaTeX ou LibreOffice, e a moldura Unicode é a principal
causa de falha de codificação nesses formatos.
"""

from __future__ import annotations

from typing import Iterable, Optional, Sequence

__all__ = ["LARGURA", "imprimir_relatorio", "imprimir_resumo", "formatar_decimal"]

#: Largura útil da saída do terminal.
LARGURA = 78


def formatar_decimal(valor: Optional[float], casas: int = 4) -> str:
    """Formata um número para exibição com casas decimais fixas.

    Um valor ``None`` aparece como ``"-"`` — a ausência é informação, e não
    zero.
    """
    if valor is None:
        return "-"
    return f"{valor:.{casas}f}"


def _linha(caractere: str = "-") -> str:
    return caractere * LARGURA


def _cabecalho(titulo: str) -> str:
    return f"\n{_linha('=')}\n{titulo.center(LARGURA)}\n{_linha('=')}"


def _tabela(cabecalhos: Sequence[str], linhas: Iterable[Sequence[str]]) -> list:
    """Monta uma tabela ASCII com colunas de largura fixa."""
    larguras = [len(cabecalho) for cabecalho in cabecalhos]
    corpo = [list(str(celula) for celula in linha) for linha in linhas]

    for linha in corpo:
        for indice, celula in enumerate(linha):
            if indice < len(larguras):
                larguras[indice] = max(larguras[indice], len(celula))

    def formatar(celulas: Sequence[str]) -> str:
        partes = []
        for indice, largura in enumerate(larguras):
            celula = celulas[indice] if indice < len(celulas) else ""
            partes.append(celula.ljust(largura))
        return "| " + " | ".join(partes) + " |"

    separador = "+" + "+".join("-" * (largura + 2) for largura in larguras) + "+"
    saida = [separador, formatar(cabecalhos), separador]
    saida.extend(formatar(linha) for linha in corpo)
    saida.append(separador)
    return saida


def imprimir_relatorio(registros: Sequence, titulo: str = "RELATORIO DE CALIBRACAO") -> None:
    """Imprime o relatório de calibração com o JOIN de 4 tabelas.

    Args:
        registros: Linhas do relatório, cada uma com as chaves ``id_medicao``,
            ``tecnico``, ``equipamento``, ``padrao``, ``caracteristica``,
            ``valor_nominal``, ``valor_obtido``, ``desvio``, ``unidade`` e
            ``status_resultado``.
        titulo: Cabeçalho do relatório.
    """
    print(_cabecalho(titulo))

    if not registros:
        print("Nenhuma medicao registrada.")
        return

    cabecalhos = [
        "ID",
        "TECNICO",
        "EQUIP.",
        "CARACTERISTICA",
        "NOMINAL",
        "OBTIDO",
        "DESVIO",
        "UN",
        "SITUACAO",
    ]
    linhas = []
    for registro in registros:
        linhas.append(
            [
                str(registro["id_medicao"]),
                str(registro["tecnico"]),
                str(registro["equipamento"]),
                str(registro["caracteristica"]),
                formatar_decimal(registro["valor_nominal"], 4),
                formatar_decimal(registro["valor_obtido"], 4),
                formatar_decimal(registro["desvio"], 4),
                str(registro["unidade"]),
                str(registro["status_resultado"]),
            ]
        )

    for linha in _tabela(cabecalhos, linhas):
        print(linha)


def imprimir_resumo(resumo: dict) -> None:
    """Imprime o resumo quantitativo do acervo."""
    print(_cabecalho("RESUMO"))
    print(f"  Total de medicoes : {resumo.get('total', 0)}")
    print(f"  Aprovadas         : {resumo.get('aprovados', 0)}")
    print(f"  Reprovadas        : {resumo.get('reprovados', 0)}")
    print(f"  Pendencias abertas: {resumo.get('pendencias', 0)}")
    print(_linha())
