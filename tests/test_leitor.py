"""Testes do leitor de planilhas.

Usa as planilhas reais da Schulz quando estão disponíveis em ``~/Downloads``;
caso contrário, constrói planilhas OOXML de teste em memória.

As planilhas reais são a evidência de que os casos do formato *strict* e dos
dois blocos de medição funcionam — são eles que quebram um leitor escrito
apenas com suposições.
"""

import sys
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from schulz_mvp.leitor_planilha import (  # noqa: E402
    FormatoArquivo,
    FormatoNaoSuportadoError,
    LeitorPlanilha,
    PlanilhaNaoReconhecidaError,
    serial_excel_para_data,
    serial_excel_para_hora,
)

DOWNLOADS = Path.home() / "Downloads"
PLANILHA_REAL = DOWNLOADS / "Registro MMC.xlsx"
PLANILHA_MODELO = DOWNLOADS / "planilha MMC.xlsm"
PLANILHA_STRICT = DOWNLOADS / "Dispositivo de controle (1).xlsx"


def _planilha_minima(caminho: Path, celulas: dict) -> Path:
    """Cria um ``.xlsx`` mínimo com as células informadas.

    Args:
        caminho: Onde gravar o arquivo.
        celulas: Dicionário ``{linha: {coluna: texto}}``.
    """
    from xml.sax.saxutils import escape

    linhas_xml = []
    for numero in sorted(celulas):
        partes = []
        for coluna in sorted(celulas[numero]):
            referencia = f"{chr(64 + coluna)}{numero}"
            valor = escape(str(celulas[numero][coluna]))
            partes.append(f'<c r="{referencia}" t="inlineStr"><is><t>{valor}</t></is></c>')
        linhas_xml.append(f'<row r="{numero}">{"".join(partes)}</row>')

    workbook = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
        ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Report" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>'
    )
    planilha = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(linhas_xml)}</sheetData></worksheet>'
    )

    with zipfile.ZipFile(caminho, "w") as pacote:
        pacote.writestr("xl/workbook.xml", workbook)
        pacote.writestr("xl/_rels/workbook.xml.rels", rels)
        pacote.writestr("xl/worksheets/sheet1.xml", planilha)
    return caminho


class TestDeteccaoDeFormato(unittest.TestCase):
    """Detecção por magic bytes, não por extensão."""

    def setUp(self):
        self.diretorio = TemporaryDirectory()
        self.raiz = Path(self.diretorio.name)

    def tearDown(self):
        self.diretorio.cleanup()

    def test_zip_e_ooxml(self):
        caminho = self.raiz / "planilha.xlsx"
        caminho.write_bytes(b"PK\x03\x04" + b"\x00" * 100)
        self.assertEqual(LeitorPlanilha.detectar_formato(caminho), FormatoArquivo.OOXML)

    def test_ole2_e_xls_legado(self):
        caminho = self.raiz / "legado.xls"
        caminho.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 100)
        self.assertEqual(LeitorPlanilha.detectar_formato(caminho), FormatoArquivo.OLE2)

    def test_texto_e_desconhecido(self):
        caminho = self.raiz / "notas.txt"
        caminho.write_text("apenas texto", encoding="utf-8")
        self.assertEqual(
            LeitorPlanilha.detectar_formato(caminho), FormatoArquivo.DESCONHECIDO
        )

    def test_extensao_enganosa_nao_muda_a_deteccao(self):
        # Um arquivo OOXML renomeado para .xls continua sendo OOXML.
        caminho = self.raiz / "fingindo.xls"
        caminho.write_bytes(b"PK\x03\x04" + b"\x00" * 100)
        self.assertEqual(LeitorPlanilha.detectar_formato(caminho), FormatoArquivo.OOXML)


class TestErrosDeLeitura(unittest.TestCase):
    """Erros de leitura viram exceções com orientação."""

    def setUp(self):
        self.diretorio = TemporaryDirectory()
        self.raiz = Path(self.diretorio.name)

    def tearDown(self):
        self.diretorio.cleanup()

    def test_arquivo_inexistente(self):
        with self.assertRaises(FormatoNaoSuportadoError):
            LeitorPlanilha().ler(self.raiz / "nao_existe.xlsx")

    def test_arquivo_que_nao_e_excel(self):
        caminho = self.raiz / "texto.txt"
        caminho.write_text("nao sou planilha", encoding="utf-8")
        with self.assertRaises(FormatoNaoSuportadoError):
            LeitorPlanilha().ler(caminho)

    def test_xls_legado_orienta_a_conversao(self):
        caminho = self.raiz / "legado.xls"
        caminho.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 100)
        with self.assertRaises(FormatoNaoSuportadoError) as contexto:
            LeitorPlanilha().ler(caminho)
        self.assertIn(".xlsx", str(contexto.exception))

    def test_zip_sem_workbook(self):
        caminho = self.raiz / "zip_sem_excel.xlsx"
        with zipfile.ZipFile(caminho, "w") as pacote:
            pacote.writestr("qualquer.txt", "conteudo")
        with self.assertRaises((FormatoNaoSuportadoError, PlanilhaNaoReconhecidaError)):
            LeitorPlanilha().ler(caminho)


class TestLeituraDePlanilhaMinima(unittest.TestCase):
    """Leitura da grade a partir de um .xlsx construído no teste."""

    def setUp(self):
        self.diretorio = TemporaryDirectory()
        self.raiz = Path(self.diretorio.name)
        self.caminho = _planilha_minima(
            self.raiz / "minima.xlsx",
            {
                1: {1: "Characteristic", 2: "Actual"},
                2: {1: "DIAMETRO", 2: "50.05"},
            },
        )

    def tearDown(self):
        self.diretorio.cleanup()

    def test_le_a_aba_pelo_nome(self):
        planilha = LeitorPlanilha().ler(self.caminho)
        self.assertIn("Report", planilha.nomes_abas)

    def test_le_os_valores_da_grade(self):
        planilha = LeitorPlanilha().ler(self.caminho)
        grade = planilha.aba("Report")
        self.assertEqual(grade[1][1], "Characteristic")
        self.assertEqual(grade[2][2], "50.05")

    def test_celula_inexistente_devolve_none(self):
        planilha = LeitorPlanilha().ler(self.caminho)
        self.assertIsNone(planilha.celula("Report", 99, 1))

    def test_aba_inexistente_levanta_erro(self):
        planilha = LeitorPlanilha().ler(self.caminho)
        with self.assertRaises(KeyError):
            planilha.aba("Outra")


class TestConversaoDeSerial(unittest.TestCase):
    """Conversão dos números de série do Excel."""

    def test_data(self):
        self.assertEqual(
            serial_excel_para_data(46247).strftime("%Y-%m-%d"), "2026-08-13"
        )

    def test_hora(self):
        self.assertEqual(
            serial_excel_para_hora(0.67807870370370371).strftime("%H:%M:%S"), "16:16:26"
        )


class TestPlanilhaDeExemplo(unittest.TestCase):
    """A planilha gerada por ``tools/gerar_planilha_exemplo.py``.

    Ela reproduz o layout Calypso/MMC e é lida tanto pelo ``openpyxl``
    quanto pelo leitor de reserva da biblioteca padrão.
    """

    @classmethod
    def setUpClass(cls):
        from schulz_mvp.etl import processar_planilha
        from tools.gerar_planilha_exemplo import gerar

        cls.diretorio = TemporaryDirectory()
        cls.caminho = gerar(Path(cls.diretorio.name) / "exemplo.xlsx")
        cls.resultado = processar_planilha(cls.caminho)

    @classmethod
    def tearDownClass(cls):
        cls.diretorio.cleanup()

    def test_le_os_dois_blocos(self):
        self.assertEqual(self.resultado.total_registros, 12)
        self.assertEqual(self.resultado.blocos, [1, 2])

    def test_le_os_metadados(self):
        metadados = self.resultado.metadados
        self.assertEqual(metadados["plano_medicao"], "PLANO_EXEMPLO")
        self.assertEqual(metadados["data_medicao"], "2026-08-13")
        self.assertEqual(metadados["metrologista"], "José A. Rosa Jr")
        self.assertEqual(metadados["mmc"], "500008")

    def test_o_openpyxl_also_le(self):
        try:
            import openpyxl
        except ImportError:
            self.skipTest("openpyxl não instalado")
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            livro = openpyxl.load_workbook(self.caminho, data_only=True)
        self.assertIn("Report", livro.sheetnames)
        self.assertEqual(livro["Report"]["B5"].value, "PLANO_EXEMPLO")
        livro.close()


@unittest.skipUnless(PLANILHA_REAL.exists(), "planilha real da Schulz indisponível")
class TestPlanilhasReais(unittest.TestCase):
    """Leitura das planilhas reais fornecidas pela empresa."""

    def test_le_o_registro_mmc(self):
        planilha = LeitorPlanilha().ler(PLANILHA_REAL)
        self.assertIn("Report", planilha.nomes_abas)
        grade = planilha.aba("Report")
        self.assertEqual(grade[13][1], "Characteristic")

    def test_le_os_valores_e_nao_os_rotulos(self):
        grade = LeitorPlanilha().ler(PLANILHA_REAL).aba("Report")
        self.assertEqual(grade[5][2], "703.1208_TESTE")
        self.assertEqual(grade[11][2], "José A. Rosa Jr")
        self.assertEqual(grade[11][4], 500008)
        self.assertEqual(grade[11][6], "CDM")
        self.assertEqual(grade[8][6], 27)

    @unittest.skipUnless(PLANILHA_MODELO.exists(), "modelo indisponível")
    def test_le_o_modelo_vazio(self):
        planilha = LeitorPlanilha().ler(PLANILHA_MODELO)
        self.assertIn("Report", planilha.nomes_abas)

    @unittest.skipUnless(PLANILHA_STRICT.exists(), "planilha strict indisponível")
    def test_le_o_ooxml_estrito(self):
        # O openpyxl devolve uma lista de abas VAZIA para o formato strict,
        # sem levantar exceção. O leitor precisa cair no fallback.
        planilha = LeitorPlanilha().ler(PLANILHA_STRICT)
        self.assertTrue(planilha.nomes_abas)
        self.assertIn("Registro", planilha.nomes_abas)

    @unittest.skipUnless(PLANILHA_STRICT.exists(), "planilha strict indisponível")
    def test_leitor_de_reserva_agora_o_formato_estrito(self):
        planilha = LeitorPlanilha().ler(PLANILHA_STRICT)
        grade = planilha.aba("Registro")
        self.assertTrue(grade)
        # A aba de registro do dispositivo de controle tem rótulos na coluna B.
        self.assertEqual(grade[5][2], "Data:")


if __name__ == "__main__":
    unittest.main()
