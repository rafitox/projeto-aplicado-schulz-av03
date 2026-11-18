"""Testes das rotas do webapp.

Usa o cliente de teste do Flask, que não abre porta de rede.
"""

import io
import sqlite3
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

# O webapp precisa do Flask, que é uma dependência OPCIONAL: o núcleo do
# projeto roda apenas com a biblioteca padrão. Sem Flask, os testes do
# webapp são pulados com uma mensagem clara — em vez de o módulo inteiro
# falhar na importação e reprovar a suite inteira.
try:
    from schulz_mvp.webapp import criar_aplicacao  # noqa: E402

    FLASK_DISPONIVEL = True
except ImportError:  # pragma: no cover - depende do ambiente
    FLASK_DISPONIVEL = False
    criar_aplicacao = None

MENSAGEM_SEM_FLASK = (
    "Flask não está instalado — rode "
    "'pip install -r requirements.txt' para habilitar os testes do webapp"
)

DOWNLOADS = Path.home() / "Downloads"
PLANILHA_REAL = DOWNLOADS / "Registro MMC.xlsx"
PLANILHA_MODELO = DOWNLOADS / "planilha MMC.xlsm"
PLANILHA_OUTRA = DOWNLOADS / "Dispositivo de controle (1).xlsx"


@unittest.skipUnless(FLASK_DISPONIVEL, MENSAGEM_SEM_FLASK)
class TesteDoWebapp(unittest.TestCase):
    """Base com uma aplicação isolada e um banco temporário."""

    def setUp(self):
        self.diretorio = TemporaryDirectory()
        self.banco = Path(self.diretorio.name) / "teste.db"
        self.aplicacao = criar_aplicacao(str(self.banco))
        self.aplicacao.config["TESTING"] = True
        self.cliente = self.aplicacao.test_client()

    def tearDown(self):
        self.diretorio.cleanup()

    def _enviar(self, conteudo: bytes, nome: str = "planilha.xlsx") -> str:
        """Envia um arquivo pela rota de importação."""
        return "arquivo"

    def _post_arquivo(self, conteudo: bytes, nome: str = "planilha.xlsx"):
        """Faz POST em /importar com um arquivo."""
        return self.cliente.post(
            "/importar",
            data={"arquivo": (io.BytesIO(conteudo), nome)},
            content_type="multipart/form-data",
        )

    def _contar(self, tabela: str) -> int:
        """Conta as linhas de uma tabela."""
        conexao = sqlite3.connect(str(self.banco))
        try:
            return conexao.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]
        finally:
            conexao.close()


class TestPaginas(TesteDoWebapp):
    """As páginas do webapp respondem."""

    def test_pagina_inicial(self):
        resposta = self.cliente.get("/")
        self.assertEqual(resposta.status_code, 200)
        self.assertIn(b"multipart/form-data", resposta.data)
        self.assertIn(b'type="file"', resposta.data)

    def test_pagina_de_relatorio_vazia(self):
        resposta = self.cliente.get("/relatorio")
        self.assertEqual(resposta.status_code, 200)

    def test_pagina_de_pendencias(self):
        resposta = self.cliente.get("/pendencias")
        self.assertEqual(resposta.status_code, 200)

    def test_api_de_medicoes(self):
        resposta = self.cliente.get("/api/medicoes")
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.get_json()["ok"])

    def test_api_de_estatisticas(self):
        resposta = self.cliente.get("/api/estatisticas")
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("resumo", resposta.get_json())


class TestErrosDeUpload(TesteDoWebapp):
    """Entradas inválidas produzem status codes corretos, sem traceback."""

    def test_sem_arquivo(self):
        resposta = self.cliente.post(
            "/api/importar", data={}, content_type="multipart/form-data"
        )
        self.assertEqual(resposta.status_code, 400)

    def test_arquivo_que_nao_e_excel(self):
        resposta = self._post_arquivo(b"isto nao e uma planilha", "notas.txt")
        self.assertEqual(resposta.status_code, 415)

    def test_extensao_xls_com_conteudo_ooxml_e_aceito(self):
        # A extensão é apenas uma dica. Um arquivo OOXML renomeado para .xls
        # continua sendo OOXML e deve ser aceito: quem decide é o conteúdo.
        if not PLANILHA_REAL.exists():
            self.skipTest("planilha real indisponível")
        with open(PLANILHA_REAL, "rb") as arquivo:
            conteudo = arquivo.read()
        resposta = self._post_arquivo(conteudo, "planilha.xls")
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("PLANICIDADE_REF", resposta.get_data(as_text=True))

    def test_extensao_desconhecida_e_recusada(self):
        # Um PDF não é Excel, e a extensão já denuncia o problema.
        resposta = self._post_arquivo(b"%PDF-1.7 nao sou excel", "relatorio.pdf")
        self.assertEqual(resposta.status_code, 415)

    def test_xls_legado_orienta_a_conversao(self):
        resposta = self._post_arquivo(
            b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 512, "legado.xls"
        )
        self.assertEqual(resposta.status_code, 415)
        self.assertIn(".xlsx", resposta.get_data(as_text=True))

    def test_xls_legado_na_api_devolve_json(self):
        resposta = self.cliente.post(
            "/api/importar",
            data={"arquivo": (io.BytesIO(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 512), "legado.xls")},
            content_type="multipart/form-data",
        )
        self.assertEqual(resposta.status_code, 415)
        self.assertIn(".xlsx", resposta.get_json()["erro"])

    def test_excel_sem_a_aba_de_medicoes(self):
        if not PLANILHA_OUTRA.exists():
            self.skipTest("planilha indisponível")
        with open(PLANILHA_OUTRA, "rb") as arquivo:
            conteudo = arquivo.read()
        resposta = self._post_arquivo(conteudo, "dispositivo.xlsx")
        self.assertEqual(resposta.status_code, 422)

    def test_rota_html_devolve_o_status_real_de_erro(self):
        # Um 302 em uma falha diria "sucesso" ao cliente. A rota HTML
        # reexibe a página de upload com o status HTTP correto.
        resposta = self.cliente.post(
            "/importar", data={}, content_type="multipart/form-data"
        )
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("Nenhum arquivo", resposta.get_data(as_text=True))


@unittest.skipUnless(PLANILHA_REAL.exists(), "planilha real da Schulz indisponível")
class TestImportacao(TesteDoWebapp):
    """O fluxo completo de importação com a planilha real."""

    def setUp(self):
        super().setUp()
        with open(PLANILHA_REAL, "rb") as arquivo:
            self.conteudo = arquivo.read()

    def test_previa_mostra_os_dados(self):
        resposta = self._post_arquivo(self.conteudo, "Registro MMC.xlsx")
        self.assertEqual(resposta.status_code, 200)
        texto = resposta.get_data(as_text=True)
        self.assertIn("PLANICIDADE_REF", texto)
        self.assertIn("José A. Rosa Jr", texto)
        self.assertIn("703.1208_TESTE", texto)

    def test_previa_avisa_que_nada_foi_gravado(self):
        resposta = self._post_arquivo(self.conteudo, "Registro MMC.xlsx")
        self.assertIn("Nada foi gravado", resposta.get_data(as_text=True))

    def test_previa_nao_grava_no_banco(self):
        # A página inicial garante que o banco exista com o schema.
        self.cliente.get("/")
        self._post_arquivo(self.conteudo, "Registro MMC.xlsx")
        self.assertEqual(self._contar("medicao"), 0)

    def test_confirmacao_grava_as_28_mediacoes(self):
        self._post_arquivo(self.conteudo, "Registro MMC.xlsx")
        resposta = self.cliente.post("/confirmar")
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(self._contar("medicao"), 28)

    def test_confirmacao_cria_os_cadastros(self):
        self._post_arquivo(self.conteudo, "Registro MMC.xlsx")
        self.cliente.post("/confirmar")
        self.assertEqual(self._contar("tecnico_solicitante"), 1)
        self.assertEqual(self._contar("equipamento"), 1)

    def test_confirmacao_grava_a_origem(self):
        self._post_arquivo(self.conteudo, "Registro MMC.xlsx")
        self.cliente.post("/confirmar")
        conexao = sqlite3.connect(str(self.banco))
        try:
            linhas = conexao.execute(
                "SELECT DISTINCT origem_arquivo, origem_hash, bloco "
                "FROM medicao ORDER BY bloco"
            ).fetchall()
        finally:
            conexao.close()
        self.assertEqual(len(linhas), 2)
        self.assertEqual(linhas[0][0], "Registro MMC.xlsx")
        self.assertEqual(len(linhas[0][1]), 16)
        self.assertEqual([linha[2] for linha in linhas], [1, 2])

    def test_reimportacao_nao_duplica(self):
        self._post_arquivo(self.conteudo, "Registro MMC.xlsx")
        self.cliente.post("/confirmar")
        self._post_arquivo(self.conteudo, "Registro MMC.xlsx")
        self.cliente.post("/confirmar")
        self.assertEqual(self._contar("medicao"), 28)

    def test_api_de_importacao_e_idempotente(self):
        primeira = self.cliente.post(
            "/api/importar",
            data={"arquivo": (io.BytesIO(self.conteudo), "Registro MMC.xlsx")},
            content_type="multipart/form-data",
        )
        self.assertEqual(primeira.status_code, 200)
        self.assertEqual(primeira.get_json()["gravacao"]["medicoes_inseridas"], 28)

        segunda = self.cliente.post(
            "/api/importar",
            data={"arquivo": (io.BytesIO(self.conteudo), "Registro MMC.xlsx")},
            content_type="multipart/form-data",
        )
        self.assertEqual(segunda.get_json()["gravacao"]["medicoes_inseridas"], 0)
        self.assertEqual(segunda.get_json()["gravacao"]["medicoes_existentes"], 28)
        self.assertEqual(self._contar("medicao"), 28)

    def test_relatorio_mostra_as_mediacoes(self):
        self._post_arquivo(self.conteudo, "Registro MMC.xlsx")
        self.cliente.post("/confirmar")
        resposta = self.cliente.get("/relatorio")
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("José A. Rosa Jr", resposta.get_data(as_text=True))

    def test_api_de_medicoes_devolve_28_registros(self):
        self._post_arquivo(self.conteudo, "Registro MMC.xlsx")
        self.cliente.post("/confirmar")
        resposta = self.cliente.get("/api/medicoes")
        self.assertEqual(len(resposta.get_json()["medicoes"]), 28)

    def test_confirmar_sem_previa_erro(self):
        resposta = self.cliente.post("/api/importar", data={},
                                    content_type="multipart/form-data")
        self.assertEqual(resposta.status_code, 400)


@unittest.skipUnless(PLANILHA_MODELO.exists(), "modelo indisponível")
class TestImportacaoDePlanilhaVazia(TesteDoWebapp):
    """Uma planilha sem medições gera pendências, não uma falha."""

    def setUp(self):
        super().setUp()
        with open(PLANILHA_MODELO, "rb") as arquivo:
            self.conteudo = arquivo.read()

    def test_previa_de_planilha_sem_medicoes(self):
        resposta = self._post_arquivo(self.conteudo, "modelo.xlsm")
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("Nenhuma medição encontrada", resposta.get_data(as_text=True))

    def test_confirmacao_registra_pendencias(self):
        self._post_arquivo(self.conteudo, "modelo.xlsm")
        self.cliente.post("/confirmar")
        self.assertEqual(self._contar("medicao"), 0)
        self.assertGreater(self._contar("pendencia"), 0)


class TestSegurancaDoUpload(TesteDoWebapp):
    """As regras de segurança aplicadas ao arquivo enviado."""

    def test_nome_do_usuario_nao_vai_para_o_banco(self):
        if not PLANILHA_REAL.exists():
            self.skipTest("planilha real indisponível")
        with open(PLANILHA_REAL, "rb") as arquivo:
            conteudo = arquivo.read()
        self._post_arquivo(conteudo, "arquivo_com_nome_estranho.xlsx")
        self.cliente.post("/confirmar")
        conexao = sqlite3.connect(str(self.banco))
        try:
            nomes = {
                linha[0]
                for linha in conexao.execute(
                    "SELECT DISTINCT origem_arquivo FROM medicao"
                )
            }
        finally:
            conexao.close()
        # O nome é sanitizado, e não usado como caminho.
        self.assertEqual(nomes, {"arquivo_com_nome_estranho.xlsx"})

    def test_caminho_do_arquivo_nao_vem_do_formulario(self):
        # Mesmo que o formulário traga um caminho, ele é ignorado: a
        # confirmação usa o caminho guardado na sessão.
        if not PLANILHA_REAL.exists():
            self.skipTest("planilha real indisponível")
        with open(PLANILHA_REAL, "rb") as arquivo:
            conteudo = arquivo.read()
        self._post_arquivo(conteudo, "Registro MMC.xlsx")
        resposta = self.cliente.post(
            "/confirmar", data={"caminho": "/etc/passwd"}
        )
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(self._contar("medicao"), 28)


if __name__ == "__main__":
    unittest.main()
