"""Testes do ETL — extração, transformação e validação.

Os casos que mais importam são os que a planilha real da Schulz expõe:
os metadados vivem na linha **depois** dos rótulos, a tabela de medições
pode ocupar **dois blocos** e o cabeçalho da linha 13 não é uma medição.
"""

import sys
import unittest
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from schulz_mvp.etl import (  # noqa: E402
    MarcadoresAusentes,
    processar_grade,
    processar_planilha,
)
from schulz_mvp.leitor_planilha import PlanilhaNaoReconhecidaError  # noqa: E402

DOWNLOADS = Path.home() / "Downloads"
PLANILHA_REAL = DOWNLOADS / "Registro MMC.xlsx"
PLANILHA_MODELO = DOWNLOADS / "planilha MMC.xlsm"


def _grade(celulas: dict) -> dict:
    """Constrói uma grade ``{linha: {coluna: valor}}``."""
    return dict(celulas)


class TestSaneamento(unittest.TestCase):
    """Limpeza dos valores vindos da planilha."""

    def test_marcadores_de_ausencia_viram_none(self):
        from schulz_mvp.etl import _limpar_texto

        for marcador in MarcadoresAusentes:
            with self.subTest(marcador=marcador):
                self.assertIsNone(_limpar_texto(marcador))

    def test_remove_caracteres_de_controle(self):
        from schulz_mvp.etl import _limpar_texto

        self.assertEqual(_limpar_texto("João\x00 da\r\nSilva"), "João da Silva")

    def test_remove_espacos_nas_pontas(self):
        from schulz_mvp.etl import _limpar_texto

        self.assertEqual(_limpar_texto("  MGM-01  "), "MGM-01")

    def test_virgula_decimal_vira_ponto(self):
        from schulz_mvp.etl import _para_decimal

        self.assertEqual(_para_decimal("50,05"), Decimal("50.05"))

    def test_formato_americano_preservado(self):
        from schulz_mvp.etl import _para_decimal

        self.assertEqual(_para_decimal("50.05"), Decimal("50.05"))

    def test_formato_brasileiro_com_milhar(self):
        from schulz_mvp.etl import _para_decimal

        self.assertEqual(_para_decimal("1.234,56"), Decimal("1234.56"))

    def test_texto_nao_numerico_vira_none(self):
        from schulz_mvp.etl import _para_decimal

        self.assertIsNone(_para_decimal("abc"))

    def test_data_em_varios_formatos(self):
        from schulz_mvp.etl import _para_data

        self.assertEqual(_para_data("2026-08-13"), "2026-08-13")
        self.assertEqual(_para_data("13/08/2026"), "2026-08-13")
        self.assertEqual(_para_data("2026/08/13"), "2026-08-13")

    def test_hora_em_varios_formatos(self):
        from schulz_mvp.etl import _para_hora

        self.assertEqual(_para_hora("16:16:26"), "16:16:26")
        self.assertEqual(_para_hora("16:16"), "16:16:00")

    def test_sinal_das_tolerancias_preservado(self):
        # RN07: o valor negativo da tolerância inferior não pode virar
        # positivo durante o saneamento.
        from schulz_mvp.etl import _para_decimal

        self.assertEqual(_para_decimal("-0.01"), Decimal("-0.01"))


class TestExtracaoDeGrade(unittest.TestCase):
    """Extração a partir de uma grade construída no teste."""

    def _grade_completa(self) -> dict:
        return _grade(
            {
                5: {2: "PLANO-TESTE", 4: "2026-08-13"},
                8: {4: "16:16:26", 6: 27},
                11: {2: "José A. Rosa Jr", 4: 500008, 6: "CDM"},
                13: {1: "Characteristic", 2: "Actual", 3: "Nominal",
                      4: "Upper Tol", 5: "Lower Tol", 6: "Deviation"},
                14: {1: "DIAMETRO", 2: 6.0787295, 3: 6.075, 4: 0.01, 5: -0.01,
                      6: 0.0037295},
            }
        )

    def test_le_os_metadados_das_celulas_de_valor(self):
        resultado = processar_grade({"Report": self._grade_completa()})
        self.assertEqual(resultado.metadados["plano_medicao"], "PLANO-TESTE")
        self.assertEqual(resultado.metadados["data_medicao"], "2026-08-13")
        self.assertEqual(resultado.metadados["hora_medicao"], "16:16:26")
        self.assertEqual(resultado.metadados["peca"], "27")
        self.assertEqual(resultado.metadados["metrologista"], "José A. Rosa Jr")
        self.assertEqual(resultado.metadados["mmc"], "500008")
        self.assertEqual(resultado.metadados["fornecedor"], "CDM")

    def test_nao_le_os_rotulos_como_valores(self):
        # Os rótulos estariam em B4/D4/B10 se a leitura estivesse errada.
        resultado = processar_grade({"Report": self._grade_completa()})
        self.assertNotEqual(resultado.metadados["plano_medicao"], "Measurement Plan")
        self.assertNotEqual(resultado.metadados["metrologista"], "Metrologista")

    def test_cabecalho_nao_vira_medicao(self):
        resultado = processar_grade({"Report": self._grade_completa()})
        self.assertEqual(resultado.total_registros, 1)
        self.assertEqual(resultado.registros[0].caracteristica, "DIAMETRO")

    def test_localiza_a_aba_pelo_cabecalho(self):
        # A aba "Outra" NÃO tem o cabeçalho: a localização precisa happen
        # pelo marcador estrutural, não pela posição da aba.
        grade = self._grade_completa()
        resultado = processar_grade(
            {"Outra": {1: {1: "sem relacao"}, 2: {1: "nada"}}, "Report": grade}
        )
        self.assertEqual(resultado.aba, "Report")
        self.assertEqual(resultado.total_registros, 1)

    def test_aba_sem_cabecalho_levanta_erro(self):
        with self.assertRaises(PlanilhaNaoReconhecidaError):
            processar_grade({"Qualquer": {1: {1: "nada a ver"}}})

    def test_linhas_consecutivas_formam_um_bloco(self):
        grade = self._grade_completa()
        grade[15] = {1: "DIAMETRO", 2: 6.0780314, 3: 6.075, 4: 0.01, 5: -0.01}
        resultado = processar_grade({"Report": grade})
        self.assertEqual(resultado.total_registros, 2)
        self.assertEqual(resultado.blocos, [1])

    def test_linha_em_branco_separa_blocos(self):
        # A linha 15 fica vazia, como na planilha real: as medições das
        # linhas 14 e 16 pertencem a blocos diferentes.
        grade = self._grade_completa()
        grade[16] = {1: "DIAMETRO", 2: 6.0780314, 3: 6.075, 4: 0.01, 5: -0.01}
        resultado = processar_grade({"Report": grade})
        self.assertEqual(resultado.total_registros, 2)
        self.assertEqual(resultado.blocos, [1, 2])
        self.assertEqual(resultado.registros[0].bloco, 1)
        self.assertEqual(resultado.registros[1].bloco, 2)
        self.assertEqual(resultado.registros[0].linha_origem, 14)
        self.assertEqual(resultado.registros[1].linha_origem, 16)

    def test_linhas_de_origem_distintas_entre_blocos(self):
        grade = self._grade_completa()
        grade[16] = {1: "DIAMETRO", 2: 6.0780314, 3: 6.075, 4: 0.01, 5: -0.01}
        resultado = processar_grade({"Report": grade})
        linhas = [registro.linha_origem for registro in resultado.registros]
        self.assertEqual(len(linhas), len(set(linhas)))

    def test_valores_numericos_convertidos(self):
        resultado = processar_grade({"Report": self._grade_completa()})
        registro = resultado.registros[0]
        self.assertEqual(registro.valor_obtido, Decimal("6.0787295"))
        self.assertEqual(registro.valor_nominal, Decimal("6.075"))
        self.assertEqual(registro.tol_superior, Decimal("0.01"))
        self.assertEqual(registro.tol_inferior, Decimal("-0.01"))

    def test_pendencia_por_campo_obrigatorio_ausente(self):
        grade = self._grade_completa()
        del grade[14][2]  # valor obtido ausente
        resultado = processar_grade({"Report": grade})
        campos = [p.campo for p in resultado.pendencias]
        self.assertIn("valor_obtido", campos)

    def test_pendencia_por_metadado_ausente(self):
        grade = self._grade_completa()
        del grade[11][4]  # MMC ausente
        resultado = processar_grade({"Report": grade})
        campos = [p.campo for p in resultado.pendencias]
        self.assertIn("mmc", campos)

    def test_tolerancia_invertida_gera_pendencia(self):
        grade = self._grade_completa()
        grade[14][4] = -0.01  # tolerância superior negativa
        grade[14][5] = 0.01   # tolerância inferior positiva
        resultado = processar_grade({"Report": grade})
        self.assertIn("tolerancia", [p.campo for p in resultado.pendencias])

    def test_registro_sem_dados_obrigatorios(self):
        grade = self._grade_completa()
        del grade[14][2]
        resultado = processar_grade({"Report": grade})
        self.assertFalse(resultado.registros[0].tem_dados_obrigatorios)


@unittest.skipUnless(PLANILHA_REAL.exists(), "planilha real da Schulz indisponível")
class TestPlanilhaReal(unittest.TestCase):
    """O ETL sobre a planilha real da empresa."""

    @classmethod
    def setUpClass(cls):
        cls.resultado = processar_planilha(PLANILHA_REAL)

    def test_extrai_as_28_mediacoes(self):
        self.assertEqual(self.resultado.total_registros, 28)

    def test_encontra_os_dois_blocos(self):
        self.assertEqual(self.resultado.blocos, [1, 2])

    def test_nao_importa_o_cabecalho(self):
        for registro in self.resultado.registros:
            self.assertNotEqual(registro.caracteristica, "Characteristic")

    def test_metadados_extraidos_corretamente(self):
        metadados = self.resultado.metadados
        self.assertEqual(metadados["plano_medicao"], "703.1208_TESTE")
        self.assertEqual(metadados["data_medicao"], "2026-08-13")
        self.assertEqual(metadados["hora_medicao"], "16:16:26")
        self.assertEqual(metadados["metrologista"], "José A. Rosa Jr")
        self.assertEqual(metadados["mmc"], "500008")
        self.assertEqual(metadados["fornecedor"], "CDM")
        self.assertEqual(metadados["peca"], "27")

    def test_linhas_de_origem_todas_distintas(self):
        linhas = [r.linha_origem for r in self.resultado.registros]
        self.assertEqual(len(linhas), len(set(linhas)))

    def test_sem_pendencias(self):
        # A planilha real tem todos os campos preenchidos.
        self.assertEqual(self.resultado.total_pendencias, 0)

    def test_hash_estavel_para_o_mesmo_arquivo(self):
        segundo = processar_planilha(PLANILHA_REAL)
        self.assertEqual(self.resultado.hash_arquivo, segundo.hash_arquivo)
        self.assertEqual(len(self.resultado.hash_arquivo), 16)

    def test_segundo_bloco_tem_valores_diferentes(self):
        # Evidence de que os dois blocos são medições distintas.
        primeiro = [r for r in self.resultado.registros if r.bloco == 1]
        segundo = [r for r in self.resultado.registros if r.bloco == 2]
        por_caracteristica_1 = {r.caracteristica: r.valor_obtido for r in primeiro}
        por_caracteristica_2 = {r.caracteristica: r.valor_obtido for r in segundo}
        self.assertEqual(set(por_caracteristica_1), set(por_caracteristica_2))
        diferencas = [
            chave
            for chave in por_caracteristica_1
            if por_caracteristica_1[chave] != por_caracteristica_2[chave]
        ]
        self.assertEqual(len(diferencas), 3)


@unittest.skipUnless(PLANILHA_MODELO.exists(), "modelo indisponível")
class TestModeloVazio(unittest.TestCase):
    """A planilha-modelo não tem medições, e isso não é erro."""

    @classmethod
    def setUpClass(cls):
        cls.resultado = processar_planilha(PLANILHA_MODELO)

    def test_zero_registros(self):
        self.assertEqual(self.resultado.total_registros, 0)

    def test_gera_pendencias_ausentes(self):
        campos = [p.campo for p in self.resultado.pendencias]
        self.assertIn("mmc", campos)
        self.assertIn("metrologista", campos)


if __name__ == "__main__":
    unittest.main()
