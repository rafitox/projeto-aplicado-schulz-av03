"""Leitura de planilhas Excel para uma grade de células.

Este módulo sabe **apenas ler**. Não conhece o formato Calypso/MMC, não
saneia dados e não fala com o banco: essas responsabilidades ficam nas
camadas ``etl`` e ``servico_importacao``.

Formato do arquivo
------------------

A detecção é feita por **magic bytes**, nunca pela extensão: um arquivo
`` spreadsheet.xlsx `` renomeado para ``.xls`` continua sendo OOXML, e
confiar no nome levaria o leitor a escolher o parser errado.

* ``PK\\x03\\x04`` — OOXML (``.xlsx``, ``.xlsm``). É um ZIP.
* ``\\xd0\\xcf\\x11\\xe0`` — OLE2, o formato binário legado ``.xls``.
* Qualquer outra assinatura — formato não suportado.

Duas variantes de OOXML
-----------------------

Existe OOXML *transitional* (namespace ``schemas.openxmlformats.org``) e
OOXML *strict* (namespace ``purl.oclc.org/ooxml/spreadsheetml/main``). Os
arquivos da Schulz usam as duas.

O ``openpyxl`` **lê** um arquivo *strict* sem levantar exceção e devolve
``sheetnames == []`` — uma lista de abas vazia. Confiar nele sem verificação
resultaria em importar zero linhas sem qualquer aviso. Por isso:

1. uma lista de abas vazia é tratada como **falha de leitura**, nunca como
   "planilha sem dados";
2. existe um leitor de reserva, implementado apenas com a biblioteca padrão,
   que identifica os elementos do XML pelo nome local da tag
   (``tag.rsplit('}', 1)[-1]``) e por isso funciona nas duas variantes.
"""

from __future__ import annotations

import warnings
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from xml.etree import ElementTree as ElementTree

__all__ = [
    "FormatoArquivo",
    "Planilha",
    "Grade",
    "LeitorPlanilha",
    "FormatoNaoSuportadoError",
    "PlanilhaNaoReconhecidaError",
    "serial_excel_para_data",
    "serial_excel_para_hora",
]

#: Assinatura de um arquivo ZIP — a base de todo OOXML.
_ASSINATURA_ZIP = b"PK\x03\x04"

#: Assinatura de um documento OLE2 — o formato binário legado ``.xls``.
_ASSINATURA_OLE2 = b"\xd0\xcf\x11\xe0"

#: Época do Excel para números de série (1899-12-30).
_EPOCA_EXCEL = datetime(1899, 12, 30)


class FormatoNaoSuportadoError(Exception):
    """O arquivo não é um Excel reconhecível, ou é um ``.xls`` legado."""


class PlanilhaNaoReconhecidaError(Exception):
    """O arquivo é um Excel válido, mas não tem o formato esperado."""


class FormatoArquivo(Enum):
    """Formatos de planilha reconhecidos pelo leitor."""

    OOXML = "ooxml"
    OLE2 = "ole2"
    DESCONHECIDO = "desconhecido"


#: Tipo de uma grade: número da linha -> número da coluna -> valor.
Grade = dict


@dataclass
class Planilha:
    """Conteúdo de um arquivo Excel lido.

    Attributes:
        abas: Nome de cada aba e sua grade de células.
        formato: Formato detectado do arquivo original.
        origem: Caminho do arquivo de onde os dados vieram.
    """

    abas: dict = field(default_factory=dict)
    formato: FormatoArquivo = FormatoArquivo.DESCONHECIDO
    origem: Optional[str] = None

    @property
    def nomes_abas(self) -> list:
        """Nomes das abas presentes no arquivo."""
        return list(self.abas)

    def aba(self, nome: str) -> Grade:
        """Devolve a grade de uma aba.

        Raises:
            KeyError: Se a aba não existir no arquivo.
        """
        if nome not in self.abas:
            raise KeyError(
                f"aba {nome!r} não encontrada. Abas disponíveis: {self.nomes_abas}"
            )
        return self.abas[nome]

    def celula(self, aba: str, linha: int, coluna: int) -> Any:
        """Devolve o valor de uma célula, ou ``None`` se estiver vazia."""
        return self.abas.get(aba, {}).get(linha, {}).get(coluna)


# ===========================================================================
# CONVERSORES DE SERIAL DO EXCEL
# ===========================================================================


def serial_excel_para_data(serial: float) -> datetime:
    """Converte um número de série do Excel em data.

    O XML de uma planilha guarda a data como o número de dias desde
    1899-12-30. O valor ``46247`` corresponde a 2026-08-13.
    """
    return _EPOCA_EXCEL + timedelta(days=float(serial))


def serial_excel_para_hora(serial: float) -> time:
    """Converte a fração de dia do Excel em horário.

    O valor ``0.67807870370370371`` corresponde a 16:16:26.
    """
    total_segundos = round(float(serial) * 86400)
    total_segundos %= 86400
    return time(
        hour=total_segundos // 3600,
        minute=(total_segundos % 3600) // 60,
        second=total_segundos % 60,
    )


def _talvez_data(valor: Any) -> Any:
    """Converte um serial do Excel em data/hora, quando reconhecível.

    Só números entre 1 e 60.000 são tratados como serial: o limite superior
    cobre o ano 2064, e evita que um valor de medição como ``46247`` seja
    confundido com uma data quando vier de uma coluna de resultado.
    """
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, (int, float, Decimal)):
        numero = float(valor)
        if 0.0 <= numero <= 1.0:
            return serial_excel_para_hora(numero)
        if 1.0 < numero <= 60000.0:
            return serial_excel_para_data(numero)
    return valor


# ===========================================================================
# LEITOR
# ===========================================================================


class LeitorPlanilha:
    """Lê planilhas Excel e devolve grades de células.

    A escolha do parser é feita por assinatura do arquivo. O ``openpyxl`` é
    usado quando disponível, porque converte datas e horários serial; o
    leitor de reserva da biblioteca padrão cobre os casos em que o
    ``openpyxl`` não está instalado ou devolve uma lista de abas vazia.
    """

    @staticmethod
    def detectar_formato(caminho: Any) -> FormatoArquivo:
        """Identifica o formato do arquivo pelos seus primeiros bytes.

        Args:
            caminho: Caminho do arquivo a inspecionar.

        Returns:
            O formato detectado.

        Raises:
            FormatoNaoSuportadoError: Se o arquivo não existir ou não
                puder ser lido.
        """
        caminho = Path(caminho)
        try:
            with caminho.open("rb") as arquivo:
                assinatura = arquivo.read(8)
        except OSError as erro:
            raise FormatoNaoSuportadoError(
                f"não foi possível ler o arquivo: {erro}"
            ) from erro

        if assinatura.startswith(_ASSINATURA_ZIP):
            return FormatoArquivo.OOXML
        if assinatura.startswith(_ASSINATURA_OLE2):
            return FormatoArquivo.OLE2
        return FormatoArquivo.DESCONHECIDO

    def ler(self, caminho: Any) -> Planilha:
        """Lê um arquivo Excel e devolve suas abas.

        Args:
            caminho: Caminho do arquivo ``.xlsx`` ou ``.xlsm``.

        Returns:
            A planilha com todas as abas lidas.

        Raises:
            FormatoNaoSuportadoError: Se o arquivo não for Excel, ou for um
                ``.xls`` binário legado.
            PlanilhaNaoReconhecidaError: Se o arquivo for um Excel válido
                mas não for possível ler suas abas.
        """
        caminho = Path(caminho)
        formato = self.detectar_formato(caminho)

        if formato is FormatoArquivo.OLE2:
            raise FormatoNaoSuportadoError(
                "arquivo .xls legado (OLE2) não é suportado. "
                "Salve a planilha como .xlsx e tente novamente."
            )
        if formato is not FormatoArquivo.OOXML:
            raise FormatoNaoSuportadoError(
                "o arquivo enviado não é uma planilha Excel (.xlsx ou .xlsm)."
            )

        abas = self._ler_com_openpyxl(caminho)
        if not abas:
            # Lista de abas vazia é falha de leitura, não "planilha sem dados".
            abas = self._ler_com_reserva(caminho)

        if not abas:
            raise PlanilhaNaoReconhecidaError(
                "não foi possível ler nenhuma aba da planilha."
            )

        return Planilha(abas=abas, formato=formato, origem=str(caminho))

    # -- estratégia 1: openpyxl -------------------------------------------

    def _ler_com_openpyxl(self, caminho: Path) -> dict:
        """Lê com ``openpyxl``. Devolve ``{}`` se a biblioteca faltar.

        O ``openpyxl`` devolve ``sheetnames == []`` nos arquivos OOXML
        *strict* sem levantar exceção. Esse resultado é tratado como falha
        pelo chamador, que aciona o leitor de reserva.
        """
        try:
            import openpyxl  # noqa: WPS433 — dependência opcional
        except ImportError:
            return {}

        # O openpyxl emite avisos sobre recursos do Excel que ele não
        # suporta (validação de dados, nomes definidos). Os avisos são
        # irrelevantes para a leitura e poluem a saída do programa.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                livro = openpyxl.load_workbook(caminho, data_only=True, read_only=True)
            except Exception:
                return {}

            abas: dict = {}
            try:
                for nome in livro.sheetnames:
                    folha = livro[nome]
                    grade: Grade = {}
                    for linha in folha.iter_rows():
                        for celula in linha:
                            if celula.value is None:
                                continue
                            grade.setdefault(celula.row, {})[celula.column] = celula.value
                    if grade:
                        abas[nome] = grade
            except Exception:
                return {}
            finally:
                try:
                    livro.close()
                except Exception:
                    pass
        return abas

    # -- estratégia 2: leitor de reserva (biblioteca padrão) ----------------

    def _ler_com_reserva(self, caminho: Path) -> dict:
        """Lê o OOXML usando apenas a biblioteca padrão.

        Identifica os elementos do XML pelo nome local da tag, o que
        funciona tanto no OOXML *transitional* quanto no *strict*.
        """
        try:
            with zipfile.ZipFile(caminho) as pacote:
                nomes = pacote.namelist()
                if "xl/workbook.xml" not in nomes:
                    raise PlanilhaNaoReconhecidaError(
                        "o arquivo não tem a estrutura de um Excel válido."
                    )
                compartilhadas = self._ler_shared_strings(pacote)
                mapa_abas = self._ler_mapa_abas(pacote)
                abas: dict = {}
                for nome, alvo in mapa_abas.items():
                    if alvo not in nomes:
                        continue
                    abas[nome] = self._ler_grade(pacote, alvo, compartilhadas)
        except zipfile.BadZipFile as erro:
            raise FormatoNaoSuportadoError(
                "o arquivo não pôde ser aberto como planilha Excel."
            ) from erro
        return {nome: grade for nome, grade in abas.items() if grade}

    @staticmethod
    def _nome_local(tag: str) -> str:
        """Nome local de uma tag XML, sem o namespace."""
        return tag.rsplit("}", 1)[-1]

    def _ler_shared_strings(self, pacote: zipfile.ZipFile) -> list:
        """Lê a tabela de strings compartilhadas do Excel."""
        if "xl/sharedStrings.xml" not in pacote.namelist():
            return []
        raiz = ElementTree.fromstring(pacote.read("xl/sharedStrings.xml"))
        strings: list = []
        for item in raiz:
            if self._nome_local(item.tag) != "si":
                continue
            partes = [
                no.text or ""
                for no in item.iter()
                if self._nome_local(no.tag) == "t"
            ]
            strings.append("".join(partes))
        return strings

    def _ler_mapa_abas(self, pacote: zipfile.ZipFile) -> dict:
        """Mapeia o nome de cada aba para o arquivo XML correspondente."""
        raiz = ElementTree.fromstring(pacote.read("xl/workbook.xml"))
        rels = ElementTree.fromstring(pacote.read("xl/_rels/workbook.xml.rels"))

        destinos = {
            rel.get("Id"): rel.get("Target")
            for rel in rels
            if rel.get("Id")
        }

        mapa: dict = {}
        for elemento in raiz.iter():
            if self._nome_local(elemento.tag) != "sheet":
                continue
            nome = elemento.get("name")
            if not nome:
                continue
            identificador = None
            for chave, valor in elemento.attrib.items():
                if self._nome_local(chave) == "id":
                    identificador = valor
                    break
            alvo = destinos.get(identificador)
            if not alvo:
                continue
            if not alvo.startswith("xl/"):
                alvo = "xl/" + alvo.lstrip("/")
            mapa[nome] = alvo
        return mapa

    def _ler_grade(
        self, pacote: zipfile.ZipFile, alvo: str, compartilhadas: list
    ) -> Grade:
        """Converte o XML de uma aba em grade ``{linha: {coluna: valor}}``."""
        raiz = ElementTree.fromstring(pacote.read(alvo))
        grade: Grade = {}

        for linha in raiz.iter():
            if self._nome_local(linha.tag) != "row":
                continue
            try:
                numero = int(linha.get("r"))
            except (TypeError, ValueError):
                continue

            celulas: dict = {}
            for celula in linha:
                if self._nome_local(celula.tag) != "c":
                    continue
                coluna = self._coluna_de_referencia(celula.get("r"))
                if coluna is None:
                    continue
                valor = self._valor_da_celula(celula, compartilhadas)
                if valor is not None:
                    celulas[coluna] = valor

            if celulas:
                grade[numero] = celulas
        return grade

    @staticmethod
    def _coluna_de_referencia(referencia: Optional[str]) -> Optional[int]:
        """Converte a referência de uma célula (``"B12"``) em número de coluna."""
        if not referencia:
            return None
        letras = "".join(caractere for caractere in referencia if caractere.isalpha())
        if not letras:
            return None
        indice = 0
        for caractere in letras.upper():
            indice = indice * 26 + (ord(caractere) - 64)
        return indice

    def _valor_da_celula(self, celula: Any, compartilhadas: list) -> Any:
        """Extrai o valor de uma célula, resolvendo strings compartilhadas."""
        tipo = celula.get("t")
        valor = None

        for filho in celula:
            nome = self._nome_local(filho.tag)
            if nome == "v":
                bruto = filho.text
                if bruto is None:
                    continue
                if tipo == "s":
                    try:
                        valor = compartilhadas[int(bruto)]
                    except (ValueError, IndexError):
                        valor = bruto
                else:
                    valor = self._converter_numero(bruto)
            elif nome == "is":
                valor = "".join(
                    no.text or ""
                    for no in filho.iter()
                    if self._nome_local(no.tag) == "t"
                )
        return valor

    @staticmethod
    def _converter_numero(bruto: str) -> Any:
        """Converte o texto de um valor numérico para ``int``/``float``.

        Números que representam data ou hora em formato serial do Excel são
        devolvidos como ``datetime``/``time``.
        """
        texto = bruto.strip()
        if not texto:
            return None
        try:
            if texto.isdigit() or (texto.startswith("-") and texto[1:].isdigit()):
                return int(texto)
            return float(texto)
        except ValueError:
            return texto
