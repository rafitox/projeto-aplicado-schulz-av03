"""Extração, transformação e validação dos dados de medição da planilha MMC.

Este módulo é **puro**: não importa Flask, não abre conexão com o banco e
não conhece a camada de apresentação. Ele recebe a grade de células lida
pelo :mod:`schulz_mvp.leitor_planilha` e devolve registros saneados e
pendências. É essa independência que permite ao mesmo ETL rodar no Colab e
dentro do webapp.

Formato da planilha Calypso/MMC
-------------------------------

Na aba ``Report``, os **rótulos** dos campos de cabeçalho ficam na linha N e
os **valores** na linha N+1:

======  ===================  ==========================================
Célula  Rótulo               Valor
======  ===================  ==========================================
``B5``  Measurement Plan     ``'703.1208_TESTE'``
``D5``  Date                 ``2026-08-13``
``F5``  Order                (vazio nos arquivos da empresa)
``B8``  Drawing No.          ``'01476543-005  Rev. C 4-21-22'``
``D8``  Time                 ``16:16:26``
``F8``  Part No.             ``27``
``B11`` Metrologista         ``'José A. Rosa Jr'``
``D11`` MMC                  ``500008``
``F11`` Fornecedor           ``'CDM'``
======  ===================  ==========================================

Ler ``B4``/``D4``/``B10`` em vez de ``B5``/``D5``/``B11`` devolve os
*rótulos* ("Measurement Plan", "Metrologista") em vez dos dados.

A tabela de medições começa na linha 13, que é o **cabeçalho**
(``Characteristic``, ``Actual``, ``Nominal``, ``Upper Tol``, ``Lower Tol``,
``Deviation``); as mediões começam na linha 14. A aba é localizada pelo
cabeçalho, nunca pela posição — a aba ``Report`` não é a primeira em todos
os arquivos.

As medições podem ocupar **blocos** separados por linha em branco, repetindo
o mesmo conjunto de características na mesma peça. Cada bloco recebe um
índice próprio.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Optional

__all__ = [
    "RegistroMedicao",
    "Pendencia",
    "ResultadoImportacao",
    "MarcadoresAusentes",
    "processar_planilha",
    "processar_grade",
]

#: Texto do cabeçalho que identifica a aba de medições.
CABECALHO_CARACTERISTICA = "Characteristic"

#: Colunas da tabela de medições, por índice (1 = coluna A).
COLUNA_CARACTERISTICA = 1
COLUNA_ATUAL = 2
COLUNA_NOMINAL = 3
COLUNA_TOL_SUPERIOR = 4
COLUNA_TOL_INFERIOR = 5
COLUNA_DESVIO = 6

#: Marcadores que a empresa usa para indicar "sem valor". Vira ``None``.
MarcadoresAusentes = frozenset(
    {"???", "----", "N/A", "n/a", "null", "NULL", "00/00/0000", "-", "--"}
)

#: Caracteres de controle que não devem ficar em um texto de cadastro.
_CARACTERES_CONTROLE = re.compile(r"[\r\n\t\x00-\x1f\x7f-\x9f]")

#: Colunas dos metadados do cabeçalho: nome -> (linha, coluna).
CELULAS_METADADOS = {
    "plano_medicao": (5, 2),
    "data_medicao": (5, 4),
    "ordem_servico": (5, 6),
    "desenho": (8, 2),
    "hora_medicao": (8, 4),
    "peca": (8, 6),
    "metrologista": (11, 2),
    "mmc": (11, 4),
    "fornecedor": (11, 6),
}


# ===========================================================================
# ESTRUTURAS
# ===========================================================================


@dataclass
class RegistroMedicao:
    """Uma linha de medição extraída e saneada da planilha."""

    caracteristica: str
    valor_obtido: Optional[Decimal] = None
    valor_nominal: Optional[Decimal] = None
    tol_superior: Optional[Decimal] = None
    tol_inferior: Optional[Decimal] = None
    desvio: Optional[Decimal] = None
    linha_origem: int = 0
    bloco: int = 1
    pendencias: list = field(default_factory=list)

    @property
    def tem_dados_obrigatorios(self) -> bool:
        """Informa se a linha tem os campos mínimos para virar medição."""
        return (
            bool(self.caracteristica)
            and self.valor_obtido is not None
            and self.valor_nominal is not None
            and self.tol_superior is not None
            and self.tol_inferior is not None
        )


@dataclass
class Pendencia:
    """Informação ausente ou inválida que impede o uso do registro."""

    campo: str
    descricao: str
    criticidade: str = "MEDIA"
    linha_origem: Optional[int] = None
    bloco: Optional[int] = None

    def as_dict(self) -> dict:
        """Converte a pendência em dicionário."""
        return {
            "campo": self.campo,
            "descricao": self.descricao,
            "criticidade": self.criticidade,
            "linha_origem": self.linha_origem,
            "bloco": self.bloco,
        }


@dataclass
class ResultadoImportacao:
    """Resultado completo do processamento de uma planilha."""

    metadados: dict = field(default_factory=dict)
    registros: list = field(default_factory=list)
    pendencias: list = field(default_factory=list)
    arquivo: str = ""
    hash_arquivo: str = ""
    aba: str = ""

    @property
    def total_registros(self) -> int:
        """Quantidade de medições extraídas."""
        return len(self.registros)

    @property
    def total_pendencias(self) -> int:
        """Quantidade de pendências detectadas."""
        return len(self.pendencias)

    @property
    def blocos(self) -> list:
        """Índices de bloco presentes na planilha."""
        return sorted({registro.bloco for registro in self.registros})

    def as_dict(self) -> dict:
        """Converte o resultado em dicionário serializável."""
        return {
            "metadados": self.metadados,
            "aba": self.aba,
            "arquivo": self.arquivo,
            "hash_arquivo": self.hash_arquivo,
            "registros": [
                {
                    "caracteristica": registro.caracteristica,
                    "valor_obtido": (
                        str(registro.valor_obtido)
                        if registro.valor_obtido is not None
                        else None
                    ),
                    "valor_nominal": (
                        str(registro.valor_nominal)
                        if registro.valor_nominal is not None
                        else None
                    ),
                    "tol_superior": (
                        str(registro.tol_superior)
                        if registro.tol_superior is not None
                        else None
                    ),
                    "tol_inferior": (
                        str(registro.tol_inferior)
                        if registro.tol_inferior is not None
                        else None
                    ),
                    "desvio": (
                        str(registro.desvio) if registro.desvio is not None else None
                    ),
                    "linha_origem": registro.linha_origem,
                    "bloco": registro.bloco,
                }
                for registro in self.registros
            ],
            "pendencias": [pendencia.as_dict() for pendencia in self.pendencias],
        }


# ===========================================================================
# SANEAMENTO
# ===========================================================================


def _limpar_texto(valor: Any) -> Optional[str]:
    """Remove caracteres de controle e normaliza os espaços.

    Um caractere de controle vira **espaço**, e não é apagado: apagar uma
    quebra de linha juntaria duas palavras ("João\\r\\nSilva" viraria
    "JoãoSilva"). Em seguida, espaços repetidos são colapsados.

    Um marcador de ausência (``???``, ``----``, ``N/A``…) é normalizado para
    ``None``: o campo não tem valor, e não tem o valor "???".
    """
    if valor is None:
        return None
    if isinstance(valor, (datetime, date, time, Decimal, int, float)):
        return str(valor)
    texto = _CARACTERES_CONTROLE.sub(" ", str(valor))
    texto = re.sub(r"[ \t]+", " ", texto).strip()
    if not texto or texto in MarcadoresAusentes:
        return None
    return texto


def _para_decimal(valor: Any) -> Optional[Decimal]:
    """Converte um valor numérico da planilha para ``Decimal``.

    Aceita vírgula decimal e converte o texto com ``str()`` para não embutir
    erro binário de ponto flutuante. Retorna ``None`` quando o valor está
    ausente ou não é numérico.
    """
    if valor is None:
        return None
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return Decimal(str(valor))
    texto = str(valor).strip().replace(".", "", 1) if _tem_um_separador(valor) else str(valor).strip()
    texto = texto.replace(",", ".")
    if not texto:
        return None
    try:
        return Decimal(texto)
    except (InvalidOperation, ValueError):
        return None


def _tem_um_separador(valor: Any) -> bool:
    """Informa se o texto tem um único separador decimal.

    ``'1.234,56'`` (formato brasileiro) precisa virar ``'1234.56'``;
    ``'50.05'`` (formato americano) precisa ser preservado.
    """
    texto = str(valor).strip()
    if "," not in texto:
        return False
    if "." not in texto:
        return True
    return texto.rfind(",") > texto.rfind(".")


def _para_data(valor: Any) -> Optional[str]:
    """Normaliza uma data para o formato ISO ``AAAA-MM-DD``.

    Aceita ``datetime``, ``date``, número de série do Excel e texto nos
    formatos ``AAAA-MM-DD``, ``DD/MM/AAAA`` e ``AAAA/MM/DD``.
    """
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.strftime("%Y-%m-%d")
    if isinstance(valor, date):
        return valor.strftime("%Y-%m-%d")
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        from .leitor_planilha import serial_excel_para_data

        try:
            return serial_excel_para_data(float(valor)).strftime("%Y-%m-%d")
        except (OverflowError, ValueError):
            return None
    texto = str(valor).strip()
    if not texto or texto in MarcadoresAusentes:
        return None
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(texto, formato).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _para_hora(valor: Any) -> Optional[str]:
    """Normaliza um horário para o formato ``HH:MM:SS``.

    Aceita ``time``, número de série do Excel e texto em ``HH:MM``/``HH:MM:SS``.
    """
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.strftime("%H:%M:%S")
    if isinstance(valor, time):
        return valor.strftime("%H:%M:%S")
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        from .leitor_planilha import serial_excel_para_hora

        try:
            return serial_excel_para_hora(float(valor)).strftime("%H:%M:%S")
        except (ValueError, OverflowError):
            return None
    texto = str(valor).strip()
    if not texto or texto in MarcadoresAusentes:
        return None
    for formato in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(texto, formato).strftime("%H:%M:%S")
        except ValueError:
            continue
    return None


def _hash_arquivo(caminho: Any) -> str:
    """SHA-256 do arquivo, reduzido aos 16 primeiros hexadecimais.

    O hash identifica a origem de uma importação. Reimportar o mesmo arquivo
    não duplica registros porque a combinação ``(origem_hash, origem_linha)``
    é única.
    """
    digest = hashlib.sha256()
    with Path(caminho).open("rb") as arquivo:
        for pedaco in iter(lambda: arquivo.read(65536), b""):
            digest.update(pedaco)
    return digest.hexdigest()[:16]


# ===========================================================================
# EXTRAÇÃO
# ===========================================================================


def _localizar_aba(abas: dict) -> tuple:
    """Encontra a aba que contém o cabeçalho de medições.

    Returns:
        Tupla ``(nome_da_aba, linha_do_cabecalho)``.

    Raises:
        PlanilhaNaoReconhecidaError: Se nenhuma aba tiver o cabeçalho.
    """
    from .leitor_planilha import PlanilhaNaoReconhecidaError

    for nome, grade in abas.items():
        for linha in sorted(grade):
            celulas = grade[linha]
            if celulas.get(COLUNA_CARACTERISTICA) == CABECALHO_CARACTERISTICA:
                return nome, linha
    raise PlanilhaNaoReconhecidaError(
        "nenhuma aba da planilha contém o cabeçalho 'Characteristic'. "
        "O arquivo não parece ser uma planilha de medição da MMC."
    )


def _extrair_metadados(grade: dict) -> dict:
    """Lê os metadados das células de **valor** (linha N+1 do rótulo)."""
    metadados: dict = {}
    for nome, (linha, coluna) in CELULAS_METADADOS.items():
        bruto = grade.get(linha, {}).get(coluna)

        if nome == "data_medicao":
            metadados[nome] = _para_data(bruto)
        elif nome == "hora_medicao":
            metadados[nome] = _para_hora(bruto)
        elif nome in ("mmc", "peca"):
            # Códigos e identificadores: preservados como texto quando têm
            # zeros à esquerda, mas convertidos quando são puramente numéricos.
            texto = _limpar_texto(bruto)
            metadados[nome] = texto
        else:
            metadados[nome] = _limpar_texto(bruto)
    return metadados


def _segmentar_blocos(grade: dict, linha_inicial: int) -> list:
    """Separa as medições em blocos, delimitados por linha em branco.

    A grade só contém as linhas que têm ao menos um valor, então uma linha
    em branco simplesmente **não aparece** nela. O fim de um bloco é
    identificado pela descontinuidade da numeração: se a linha atual não é
    a seguinte à anterior, houve uma linha em branco entre elas.

    Returns:
        Lista de ``(indice_do_bloco, [(linha, celulas), ...])``.
    """
    blocos: list = []
    bloco_atual: list = []
    numero_bloco = 1
    linha_anterior: Optional[int] = None

    linhas = sorted(linha for linha in grade if linha >= linha_inicial)
    for linha in linhas:
        celulas = grade[linha]
        tem_conteudo = any(
            valor is not None and str(valor).strip() != ""
            for valor in celulas.values()
        )
        if not tem_conteudo:
            if bloco_atual:
                blocos.append((numero_bloco, bloco_atual))
                numero_bloco += 1
                bloco_atual = []
            linha_anterior = linha
            continue

        # Descontinuidade de numeração = linha em branco = novo bloco.
        if linha_anterior is not None and linha != linha_anterior + 1 and bloco_atual:
            blocos.append((numero_bloco, bloco_atual))
            numero_bloco += 1
            bloco_atual = []

        bloco_atual.append((linha, celulas))
        linha_anterior = linha

    if bloco_atual:
        blocos.append((numero_bloco, bloco_atual))
    return blocos


def _construir_registro(
    linha: int, celulas: dict, numero_bloco: int
) -> tuple:
    """Constrói um registro a partir de uma linha da tabela de medições.

    Returns:
        Tupla ``(registro, pendencias)``.
    """
    caracteristica = _limpar_texto(celulas.get(COLUNA_CARACTERISTICA))
    valor_obtido = _para_decimal(celulas.get(COLUNA_ATUAL))
    valor_nominal = _para_decimal(celulas.get(COLUNA_NOMINAL))
    tol_superior = _para_decimal(celulas.get(COLUNA_TOL_SUPERIOR))
    tol_inferior = _para_decimal(celulas.get(COLUNA_TOL_INFERIOR))
    desvio = _para_decimal(celulas.get(COLUNA_DESVIO))

    registro = RegistroMedicao(
        caracteristica=caracteristica or "",
        valor_obtido=valor_obtido,
        valor_nominal=valor_nominal,
        tol_superior=tol_superior,
        tol_inferior=tol_inferior,
        desvio=desvio,
        linha_origem=linha,
        bloco=numero_bloco,
    )

    pendencias: list = []

    if not caracteristica:
        pendencias.append(
            Pendencia(
                campo="caracteristica",
                descricao=(
                    f"Linha {linha}: a característica avaliada está vazia — "
                    "não é possível identificar a medição."
                ),
                criticidade="ALTA",
                linha_origem=linha,
                bloco=numero_bloco,
            )
        )

    for nome, valor, rotulo in (
        ("valor_obtido", valor_obtido, "valor obtido"),
        ("valor_nominal", valor_nominal, "valor nominal"),
        ("tol_superior", tol_superior, "tolerância superior"),
        ("tol_inferior", tol_inferior, "tolerância inferior"),
    ):
        if valor is None:
            pendencias.append(
                Pendencia(
                    campo=nome,
                    descricao=(
                        f"Linha {linha}: {rotulo} ausente ou não numérico — "
                        "a medição não pode ser avaliada."
                    ),
                    criticidade="ALTA",
                    linha_origem=linha,
                    bloco=numero_bloco,
                )
            )

    if (
        tol_superior is not None
        and tol_inferior is not None
        and tol_inferior > tol_superior
    ):
        pendencias.append(
            Pendencia(
                campo="tolerancia",
                descricao=(
                    f"Linha {linha}: tolerância inferior maior que a superior — "
                    "os limites de aceitação estão invertidos."
                ),
                criticidade="ALTA",
                linha_origem=linha,
                bloco=numero_bloco,
            )
        )

    registro.pendencias = pendencias
    return registro, pendencias


# ===========================================================================
# PROCESSAMENTO
# ===========================================================================


def processar_grade(
    abas: dict,
    arquivo: str = "",
    hash_arquivo: str = "",
) -> ResultadoImportacao:
    """Processa a grade de uma planilha de medição.

    Args:
        abas: Dicionário ``{nome_da_aba: grade}``.
        arquivo: Nome do arquivo de origem, para rastreabilidade.
        hash_arquivo: SHA-256 do arquivo, para idempotência da importação.

    Returns:
        O resultado da importação, com metadados, registros e pendências.

    Raises:
        PlanilhaNaoReconhecidaError: Se a aba de medições não for encontrada.
    """
    nome_aba, linha_cabecalho = _localizar_aba(abas)
    grade = abas[nome_aba]

    metadados = _extrair_metadados(grade)
    registros: list = []
    pendencias: list = []

    for numero_bloco, linhas in _segmentar_blocos(grade, linha_cabecalho + 1):
        for linha, celulas in linhas:
            registro, pendencias_linha = _construir_registro(
                linha, celulas, numero_bloco
            )
            registros.append(registro)
            pendencias.extend(pendencias_linha)

    # Metadados obrigatórios do processo: sem eles a medição fica órfã.
    if not metadados.get("mmc"):
        pendencias.append(
            Pendencia(
                campo="mmc",
                descricao=(
                    "A planilha não informa o código da MMC — não é possível "
                    "relacionar as medições ao equipamento utilizado (RN02)."
                ),
                criticidade="ALTA",
            )
        )
    if not metadados.get("data_medicao"):
        pendencias.append(
            Pendencia(
                campo="data_medicao",
                descricao=(
                    "A planilha não informa a data da medição — campo "
                    "obrigatório do registro (RN04)."
                ),
                criticidade="ALTA",
            )
        )
    if not metadados.get("metrologista"):
        pendencias.append(
            Pendencia(
                campo="metrologista",
                descricao=(
                    "A planilha não informa o metrologista responsável — "
                    "não é possível atribuir a medição a um técnico (RN02)."
                ),
                criticidade="ALTA",
            )
        )

    return ResultadoImportacao(
        metadados=metadados,
        registros=registros,
        pendencias=pendencias,
        arquivo=arquivo,
        hash_arquivo=hash_arquivo,
        aba=nome_aba,
    )


def processar_planilha(caminho: Any) -> ResultadoImportacao:
    """Lê e processa um arquivo de planilha de medição.

    Args:
        caminho: Caminho do arquivo ``.xlsx`` ou ``.xlsm``.

    Returns:
        O resultado da importação.

    Raises:
        FormatoNaoSuportadoError: Se o arquivo não for Excel suportado.
        PlanilhaNaoReconhecidaError: Se a aba de medições não for encontrada.
    """
    from .leitor_planilha import LeitorPlanilha

    caminho = Path(caminho)
    planilha = LeitorPlanilha().ler(caminho)
    return processar_grade(
        planilha.abas,
        arquivo=caminho.name,
        hash_arquivo=_hash_arquivo(caminho),
    )
