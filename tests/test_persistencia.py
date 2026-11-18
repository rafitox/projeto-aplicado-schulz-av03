"""Testes da camada de persistência SQLite.

Usa um banco em memória (``:memory:``) para não deixar arquivos para trás.
"""

import sqlite3
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from schulz_mvp._loader import carregar_modulo  # noqa: E402

classes = carregar_modulo("04_classes")


class TesteDePersistencia(unittest.TestCase):
    """Base com um banco em memória e o schema v3 criado."""

    def setUp(self):
        self.conexao = classes.ConexaoSQLite(":memory:", criar_schema=True)
        self.conexao.__enter__()
        self.servico = classes.ServicoCalibracao(self.conexao)

    def tearDown(self):
        self.conexao.__exit__(None, None, None)

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


class TestConexao(TesteDePersistencia):
    """Comportamento do gerenciador de conexão."""

    def test_pragma_de_chave_estrangeira_ligado(self):
        # O PRAGMA é por conexão: se não for ligado aqui, as FKs não valem.
        ativo = self.conexao.consultar("PRAGMA foreign_keys")[0][0]
        self.assertEqual(ativo, 1)

    def test_row_factory_ativo(self):
        linha = self.conexao.consultar("SELECT 1 AS valor")[0]
        self.assertEqual(linha["valor"], 1)

    def test_consulta_com_parametro(self):
        self.conexao.executar(
            "INSERT INTO tecnico_solicitante (nome, codigo, setor) VALUES (?, ?, ?)",
            ("João", "TEC001", "Metrologia"),
        )
        linhas = self.conexao.consultar(
            "SELECT nome FROM tecnico_solicitante WHERE codigo = ?", ("TEC001",)
        )
        self.assertEqual(len(linhas), 1)

    def test_transacao_desfaz_em_erro(self):
        self.conexao.executar(
            "INSERT INTO tecnico_solicitante (nome, codigo, setor) VALUES (?, ?, ?)",
            ("João", "TEC001", "Metrologia"),
        )
        with self.assertRaises(RuntimeError):
            with self.conexao.em_transacao():
                self.conexao.executar(
                    "INSERT INTO tecnico_solicitante (nome, codigo, setor) VALUES (?, ?, ?)",
                    ("Carlos", "TEC002", "Qualidade"),
                )
                raise RuntimeError("falha simulada")
        linhas = self.conexao.consultar("SELECT nome FROM tecnico_solicitante")
        self.assertEqual(len(linhas), 1)

    def test_erro_do_driver_vira_excecao_de_dominio(self):
        with self.assertRaises(classes.PersistenciaError):
            self.conexao.consultar("SELECT * FROM tabela_que_nao_existe")

    def test_sql_injection_e_tratado(self):
        # O parâmetro é tratado como dado, nunca como SQL: a consulta roda,
        # devolve zero linhas e a tabela continua de pé.
        linhas = self.conexao.consultar(
            "SELECT * FROM tecnico_solicitante WHERE codigo = ?",
            ("'; DROP TABLE tecnico_solicitante; --",),
        )
        self.assertEqual(linhas, [])
        self.conexao.consultar("SELECT nome FROM tecnico_solicitante")


class TestIntegridadeReferencial(TesteDePersistencia):
    """Chaves estrangeiras e restrições de unicidade."""

    def test_tecnico_inexistente_e_barrado(self):
        with self.assertRaises(classes.ReferenciaInvalidaError):
            self.servico.medicoes.inserir(self._medicao(id_tecnico=999))

    def test_equipamento_inexistente_e_barrado(self):
        with self.assertRaises(classes.ReferenciaInvalidaError):
            self.servico.medicoes.inserir(self._medicao(id_equipamento=999))

    def test_codigo_de_tecnico_duplicado_e_barrado(self):
        # O serviço reaproveita o cadastro existente (a importação é
        # idempotente); quem barra a duplicata é o repositório.
        self.servico.registrar_tecnico(classes.Tecnico(nome="João", matricula="TEC001"))
        with self.assertRaises(classes.RegistroDuplicadoError):
            self.servico.tecnicos.inserir(
                classes.Tecnico(nome="Outro", matricula="TEC001")
            )

    def test_numero_de_serie_duplicado_e_barrado(self):
        self.servico.registrar_equipamento(
            classes.Equipamento(codigo_tag="MMC001", descricao="MMC", numero_serie="SN001")
        )
        with self.assertRaises(classes.RegistroDuplicadoError):
            self.servico.registrar_equipamento(
                classes.Equipamento(codigo_tag="MMC002", descricao="MMC2", numero_serie="SN001")
            )

    def test_status_invalido_e_barrado_pelo_check(self):
        id_tecnico = self.servico.registrar_tecnico(
            classes.Tecnico(nome="João", matricula="TEC001")
        )
        id_equipamento = self.servico.registrar_equipamento(
            classes.Equipamento(codigo_tag="MMC001", descricao="MMC")
        )
        with self.assertRaises(classes.ValidacaoError):
            self.conexao.executar(
                """
                INSERT INTO medicao (id_tecnico, id_equipamento, data_medicao,
                    caracteristica, valor_nominal, tol_superior, tol_inferior,
                    valor_obtido, unidade, status_resultado)
                VALUES (?, ?, '2026-10-04', 'X', 1.0, 0.1, -0.1, 1.0, 'mm', 'TALVEZ')
                """,
                (id_tecnico, id_equipamento),
            )

    def test_data_invalida_e_barrada_pelo_check(self):
        id_tecnico = self.servico.registrar_tecnico(
            classes.Tecnico(nome="João", matricula="TEC001")
        )
        id_equipamento = self.servico.registrar_equipamento(
            classes.Equipamento(codigo_tag="MMC001", descricao="MMC")
        )
        with self.assertRaises(classes.ValidacaoError):
            self.conexao.executar(
                """
                INSERT INTO medicao (id_tecnico, id_equipamento, data_medicao,
                    caracteristica, valor_nominal, tol_superior, tol_inferior,
                    valor_obtido, unidade, status_resultado)
                VALUES (?, ?, '04/10/2026', 'X', 1.0, 0.1, -0.1, 1.0, 'mm', 'APROVADO')
                """,
                (id_tecnico, id_equipamento),
            )


class TestIdempotenciaDeImportacao(TesteDePersistencia):
    """A constraint de origem impede a duplicação (RN21)."""

    def test_mesma_origem_e_linha_e_barrada(self):
        id_tecnico = self.servico.registrar_tecnico(
            classes.Tecnico(nome="João", matricula="TEC001")
        )
        id_equipamento = self.servico.registrar_equipamento(
            classes.Equipamento(codigo_tag="MMC001", descricao="MMC")
        )
        medicao = self._medicao(
            id_tecnico=id_tecnico,
            id_equipamento=id_equipamento,
            origem_hash="abc123",
            origem_linha=14,
        )
        self.servico.medicoes.inserir(medicao)
        with self.assertRaises(classes.RegistroDuplicadoError):
            self.servico.medicoes.inserir(
                self._medicao(
                    id_tecnico=id_tecnico,
                    id_equipamento=id_equipamento,
                    origem_hash="abc123",
                    origem_linha=14,
                    caracteristica="Outra",
                )
            )

    def test_linhas_diferentes_do_mesmo_arquivo_coexistem(self):
        # Os dois blocos da planilha MMC têm linhas de origem distintas.
        id_tecnico = self.servico.registrar_tecnico(
            classes.Tecnico(nome="João", matricula="TEC001")
        )
        id_equipamento = self.servico.registrar_equipamento(
            classes.Equipamento(codigo_tag="MMC001", descricao="MMC")
        )
        self.servico.medicoes.inserir(
            self._medicao(
                id_tecnico=id_tecnico,
                id_equipamento=id_equipamento,
                origem_hash="abc123",
                origem_linha=14,
                bloco=1,
            )
        )
        self.servico.medicoes.inserir(
            self._medicao(
                id_tecnico=id_tecnico,
                id_equipamento=id_equipamento,
                origem_hash="abc123",
                origem_linha=29,
                bloco=2,
            )
        )
        self.assertEqual(len(self.servico.medicoes.listar()), 2)

    def test_ja_importado_consulta(self):
        id_tecnico = self.servico.registrar_tecnico(
            classes.Tecnico(nome="João", matricula="TEC001")
        )
        id_equipamento = self.servico.registrar_equipamento(
            classes.Equipamento(codigo_tag="MMC001", descricao="MMC")
        )
        self.servico.medicoes.inserir(
            self._medicao(
                id_tecnico=id_tecnico,
                id_equipamento=id_equipamento,
                origem_hash="abc123",
                origem_linha=14,
            )
        )
        self.assertTrue(self.servico.medicoes.ja_importado("abc123", 14))
        self.assertFalse(self.servico.medicoes.ja_importado("abc123", 29))
        self.assertFalse(self.servico.medicoes.ja_importado("outro", 14))


class TestServicoCalibracao(TesteDePersistencia):
    """Regras de orquestração do serviço."""

    def setUp(self):
        super().setUp()
        self.id_tecnico = self.servico.registrar_tecnico(
            classes.Tecnico(nome="João da Silva", matricula="TEC001", setor="Metrologia")
        )
        self.id_equipamento = self.servico.registrar_equipamento(
            classes.Equipamento(codigo_tag="MMC001", descricao="Máquina de Medição")
        )
        self.id_padrao = self.servico.registrar_padrao(
            classes.Padrao(codigo="PAD001", modelo="Bloco 50 mm")
        )

    def test_cadastros_sao_reaproveitados(self):
        id_tecnico = self.servico.registrar_tecnico(
            classes.Tecnico(nome="João da Silva", matricula="TEC001")
        )
        self.assertEqual(id_tecnico, self.id_tecnico)
        self.assertEqual(len(self.servico.tecnicos.listar()), 1)

    def test_medicao_calcula_e_grava(self):
        id_medicao = self.servico.registrar_medicao(
            self._medicao(id_tecnico=self.id_tecnico, id_equipamento=self.id_equipamento)
        )
        medicao = self.servico.medicoes.buscar_por_id(id_medicao)
        self.assertEqual(medicao.status_resultado(), "APROVADO")
        self.assertAlmostEqual(float(medicao.desvio()), 0.015, places=6)

    def test_relatorio_traz_JOIN_de_4_tabelas(self):
        self.servico.registrar_medicao(
            self._medicao(
                id_tecnico=self.id_tecnico,
                id_equipamento=self.id_equipamento,
                id_padrao=self.id_padrao,
            )
        )
        relatorio = self.servico.consultar_relatorio()
        self.assertEqual(len(relatorio), 1)
        linha = relatorio[0]
        self.assertEqual(linha["tecnico"], "João da Silva")
        self.assertEqual(linha["equipamento"], "MMC001")
        self.assertEqual(linha["padrao"], "PAD001")

    def test_aprovacao_grava_certificado(self):
        id_medicao = self.servico.registrar_medicao(
            self._medicao(id_tecnico=self.id_tecnico, id_equipamento=self.id_equipamento)
        )
        aprovada = self.servico.aprovar_medicao(
            id_medicao=id_medicao, usuario="João da Silva", certificado_numero="CERT001"
        )
        self.assertEqual(aprovada.certificado_numero, "CERT001")
        self.assertEqual(aprovada.usuario_aprovacao, "João da Silva")
        self.assertIsNotNone(aprovada.data_aprovacao)
        self.assertIsNotNone(aprovada.certificado_data)

    def test_aprovacao_bloqueada_por_pendencia(self):
        id_medicao = self.servico.registrar_medicao(
            self._medicao(id_tecnico=self.id_tecnico, id_equipamento=self.id_equipamento)
        )
        self.servico.registrar_pendencia(
            campo="padrao",
            descricao="Sem padrão vinculado",
            criticidade="ALTA",
            id_medicao=id_medicao,
        )
        with self.assertRaises(classes.PendenciaAbertaError):
            self.servico.aprovar_medicao(
                id_medicao=id_medicao, usuario="João", certificado_numero="CERT002"
            )

    def test_aprovacao_possivel_apos_resolver_a_pendencia(self):
        id_medicao = self.servico.registrar_medicao(
            self._medicao(id_tecnico=self.id_tecnico, id_equipamento=self.id_equipamento)
        )
        id_pendencia = self.servico.registrar_pendencia(
            campo="padrao",
            descricao="Sem padrão vinculado",
            id_medicao=id_medicao,
        )
        self.servico.pendencias.resolver(id_pendencia, "RESOLVIDA")
        aprovada = self.servico.aprovar_medicao(
            id_medicao=id_medicao, usuario="João", certificado_numero="CERT003"
        )
        self.assertEqual(aprovada.certificado_numero, "CERT003")

    def test_historico_registra_as_acoes(self):
        id_medicao = self.servico.registrar_medicao(
            self._medicao(id_tecnico=self.id_tecnico, id_equipamento=self.id_equipamento)
        )
        self.servico.aprovar_medicao(
            id_medicao=id_medicao, usuario="João", certificado_numero="CERT004"
        )
        acoes = [linha["acao"] for linha in self.servico.historico.listar_todos()]
        self.assertIn("MEDICAO_REGISTRADA", acoes)
        self.assertIn("CERTIFICADO_EMITIDO", acoes)

    def test_resumo_conta_o_acervo(self):
        self.servico.registrar_medicao(
            self._medicao(id_tecnico=self.id_tecnico, id_equipamento=self.id_equipamento)
        )
        self.servico.registrar_medicao(
            self._medicao(
                id_tecnico=self.id_tecnico,
                id_equipamento=self.id_equipamento,
                caracteristica="Comprimento",
                valor_obtido=100.115,
                valor_nominal=100.0,
                tol_inferior=-0.10,
                tol_superior=0.10,
            )
        )
        resumo = self.servico.resumo()
        self.assertEqual(resumo["total"], 2)
        self.assertEqual(resumo["aprovados"], 1)
        self.assertEqual(resumo["reprovados"], 1)
        self.assertEqual(resumo["pendencias"], 0)

    def test_padrao_com_calibracao_vencida(self):
        self.servico.registrar_padrao(
            classes.Padrao(
                codigo="PAD002",
                modelo="Bloco 25 mm",
                proxima_calibracao="2020-01-01",
            )
        )
        vencidos = self.servico.padroes.calibracao_vencida("2026-11-17")
        self.assertEqual(len(vencidos), 1)
        self.assertEqual(vencidos[0]["codigo"], "PAD002")

    def test_pendencias_agrupadas_por_campo(self):
        self.servico.registrar_pendencia(campo="mmc", descricao="Falta a MMC")
        self.servico.registrar_pendencia(campo="mmc", descricao="Falta a MMC de novo")
        self.servico.registrar_pendencia(campo="data", descricao="Falta a data")
        agrupadas = {linha["campo"]: linha["quantidade"] for linha in
                     self.servico.pendencias.agrupar_por_campo()}
        self.assertEqual(agrupadas["mmc"], 2)
        self.assertEqual(agrupadas["data"], 1)


if __name__ == "__main__":
    unittest.main()
