"""Testes das regras de negócio metrológicas.

Cobre as entidades e o veredito de tolerância, sem tocar no banco. O módulo
``04_classes`` é carregado pelo carregador do pacote porque o nome começa
com dígito.
"""

import sys
import unittest
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from schulz_mvp._loader import carregar_modulo  # noqa: E402

classes = carregar_modulo("04_classes")


class TestParaDecimal(unittest.TestCase):
    """Conversão para Decimal sem embutir erro binário de float."""

    def test_converte_string_decimal(self):
        self.assertEqual(classes.para_decimal("50.05"), Decimal("50.05"))

    def test_converte_com_virgula(self):
        self.assertEqual(classes.para_decimal("50,05"), Decimal("50.05"))

    def test_preserva_precisao_de_float(self):
        # Decimal(0.1) guardaria o valor binário exato; Decimal(str(0.1)) não.
        self.assertEqual(str(classes.para_decimal(0.1)), "0.1")

    def test_none_permanece_none(self):
        self.assertIsNone(classes.para_decimal(None))

    def test_texto_nao_numerico_levanta_erro(self):
        with self.assertRaises(classes.ValidacaoError):
            classes.para_decimal("abc")


class TestTecnico(unittest.TestCase):
    """Cadastro do técnico ou solicitante."""

    def test_nome_obrigatorio(self):
        with self.assertRaises(classes.ValidacaoError):
            classes.Tecnico(nome="", matricula="TEC001")

    def test_codigo_obrigatorio(self):
        with self.assertRaises(classes.ValidacaoError):
            classes.Tecnico(nome="João", matricula="")

    def test_matricula_expoe_o_codigo(self):
        tecnico = classes.Tecnico(nome="João da Silva", matricula="TEC001")
        self.assertEqual(tecnico.matricula, "TEC001")

    def test_round_trip_pelo_banco(self):
        tecnico = classes.Tecnico(nome="João", matricula="TEC001", setor="Metrologia")
        linha = dict(tecnico.to_row(), id_tecnico=7)
        recuperado = classes.Tecnico.from_row(linha)
        self.assertEqual(recuperado.nome, "João")
        self.assertEqual(recuperado.setor, "Metrologia")
        self.assertEqual(recuperado.id_tecnico, 7)


class TestEquipamento(unittest.TestCase):
    """Cadastro do equipamento."""

    def test_codigo_obrigatorio(self):
        with self.assertRaises(classes.ValidacaoError):
            classes.Equipamento(codigo_tag="", descricao="MMC")

    def test_alias_do_roteiro(self):
        equipamento = classes.Equipamento(codigo_tag="MMC001", descricao="Máquina")
        self.assertEqual(equipamento.codigo_tag, "MMC001")
        self.assertEqual(equipamento.descricao, "Máquina")


class TestPadrao(unittest.TestCase):
    """Cadastro do padrão de medição (rastreabilidade metrológica)."""

    def test_modelo_obrigatorio(self):
        with self.assertRaises(classes.ValidacaoError):
            classes.Padrao(codigo="PAD001", modelo="")

    def test_data_invalida_rejeitada(self):
        with self.assertRaises(classes.ValidacaoError):
            classes.Padrao(codigo="PAD001", modelo="Bloco", ultima_calibracao="2026-13-45")


class TestMedicaoValidacao(unittest.TestCase):
    """Validação dos campos da medição (RN04, RN06, RN07)."""

    def _medicao(self, **ajustes):
        base = dict(
            id_tecnico=1,
            id_equipamento=1,
            caracteristica="Diâmetro",
            valor_nominal=50.00,
            tol_inferior=-0.05,
            tol_superior=0.05,
            valor_obtido=50.015,
            unidade="mm",
            data_medicao="2026-10-04",
        )
        base.update(ajustes)
        return classes.Medicao(**base)

    def test_data_invalida_rejeitada(self):
        with self.assertRaises(classes.ValidacaoError):
            self._medicao(data_medicao="2026-13-45")

    def test_hora_invalida_rejeitada(self):
        with self.assertRaises(classes.ValidacaoError):
            self._medicao(hora_medicao="25:99:99")

    def test_caracteristica_obrigatoria(self):
        with self.assertRaises(classes.ValidacaoError):
            self._medicao(caracteristica="  ")

    def test_unidade_obrigatoria(self):
        with self.assertRaises(classes.ValidacaoError):
            self._medicao(unidade="")

    def test_tolerancia_invertida_rejeitada(self):
        with self.assertRaises(classes.ValidacaoError):
            self._medicao(tol_inferior=0.10, tol_superior=-0.05)

    def test_sinal_das_tolerancias_preservado(self):
        # RN07: a tolerância inferior é negativa por convenção e o valor
        # não pode ser normalizado com abs().
        medicao = self._medicao(tol_inferior=-0.05, tol_superior=0.05)
        self.assertEqual(medicao.tol_inferior, -0.05)
        self.assertLess(medicao.limite_inferior(), medicao.limite_superior())

    def test_bloco_deve_ser_positivo(self):
        with self.assertRaises(classes.ValidacaoError):
            self._medicao(bloco=0)


class TestMedicaoCalculos(unittest.TestCase):
    """Cálculos de média, desvio e desvio-padrão (RN09, RN10)."""

    def _medicao(self, **ajustes):
        base = dict(
            id_tecnico=1,
            id_equipamento=1,
            caracteristica="Diâmetro",
            valor_nominal=50.00,
            tol_inferior=-0.05,
            tol_superior=0.05,
            valor_obtido=50.015,
            unidade="mm",
            data_medicao="2026-10-04",
        )
        base.update(ajustes)
        return classes.Medicao(**base)

    def test_media_das_duas_medidas(self):
        medicao = self._medicao(medida_1=50.02, medida_2=50.01)
        self.assertEqual(medicao.media(), Decimal("50.015"))

    def test_media_ignora_medida_ausente(self):
        medicao = self._medicao(medida_1=50.02, medida_2=None)
        self.assertEqual(medicao.media(), Decimal("50.02"))

    def test_media_sem_nenhuma_medida(self):
        self.assertIsNone(self._medicao(medida_1=None, medida_2=None).media())

    def test_desvio_e_a_diferenca_para_o_nominal(self):
        self.assertEqual(self._medicao().desvio(), Decimal("0.015"))

    def test_desvio_padrao_amostral_com_duas_medidas(self):
        medicao = self._medicao(medida_1=50.02, medida_2=50.01)
        # statistics.stdev([50.02, 50.01]) = sqrt(0.00005) ≈ 0.0070710678
        self.assertAlmostEqual(float(medicao.desvio_padrao()), 0.0070710678, places=9)

    def test_desvio_padrao_exige_duas_medidas(self):
        medicao = self._medicao(medida_1=50.02, medida_2=None)
        self.assertIsNone(medicao.desvio_padrao())

    def test_limites_soma_as_tolerancias(self):
        medicao = self._medicao(valor_nominal=50.00, tol_inferior=-0.05, tol_superior=0.05)
        self.assertEqual(medicao.limite_inferior(), Decimal("49.95"))
        self.assertEqual(medicao.limite_superior(), Decimal("50.05"))


class TestMedicaoAvaliacao(unittest.TestCase):
    """Veredito APROVADO/REPROVADO (RN11)."""

    def _medicao(self, valor_obtido):
        return classes.Medicao(
            id_tecnico=1,
            id_equipamento=1,
            caracteristica="Diâmetro",
            valor_nominal=50.00,
            tol_inferior=-0.05,
            tol_superior=0.05,
            valor_obtido=valor_obtido,
            unidade="mm",
            data_medicao="2026-10-04",
        )

    def test_dentro_da_tolerancia_aprovado(self):
        self.assertEqual(self._medicao(50.015).avaliar(), "APROVADO")

    def test_exatamente_no_limite_superior_aprovado(self):
        # O intervalo é inclusivo: um resultado sobre o limite é aprovado.
        self.assertEqual(self._medicao(50.05).avaliar(), "APROVADO")

    def test_exatamente_no_limite_inferior_aprovado(self):
        self.assertEqual(self._medicao(49.95).avaliar(), "APROVADO")

    def test_acima_do_limite_superior_reprovado(self):
        self.assertEqual(self._medicao(50.06).avaliar(), "REPROVADO")

    def test_abaixo_do_limite_inferior_reprovado(self):
        self.assertEqual(self._medicao(49.94).avaliar(), "REPROVADO")

    def test_fronteira_decimal_nao_sofre_erro_de_float(self):
        # Em float, 0.1 + 0.2 <= 0.3 é False; em Decimal é True. Uma peça
        # exatamente no limite seria reprovada pela comparação em float.
        medicao = classes.Medicao(
            id_tecnico=1,
            id_equipamento=1,
            caracteristica="Teste",
            valor_nominal=0.0,
            tol_inferior=0.0,
            tol_superior=0.3,
            valor_obtido=0.3,
            unidade="mm",
            data_medicao="2026-10-04",
        )
        self.assertEqual(medicao.avaliar(), "APROVADO")
        self.assertFalse(0.1 + 0.2 <= 0.3)  # a comparação em float falharia

    def test_status_resultado_mesma_regra(self):
        medicao = self._medicao(50.015)
        self.assertEqual(medicao.status_resultado(), medicao.avaliar())


class TestHierarquiaDeExcecoes(unittest.TestCase):
    """A hierarquia de exceções do domínio."""

    def test_todas_herdam_de_calibracao_error(self):
        for nome in (
            "ValidacaoError",
            "RegraMetrologicaError",
            "PersistenciaError",
            "PendenciaAbertaError",
        ):
            with self.subTest(excecao=nome):
                excecao = getattr(classes, nome)
                self.assertTrue(issubclass(excecao, classes.CalibracaoError))

    def test_erros_de_persistencia_herdam_de_persistencia_error(self):
        for nome in ("RegistroDuplicadoError", "ReferenciaInvalidaError"):
            with self.subTest(excecao=nome):
                excecao = getattr(classes, nome)
                self.assertTrue(issubclass(excecao, classes.PersistenciaError))


if __name__ == "__main__":
    unittest.main()
