"""Interface web do MVP de calibração da Schulz S.A.

Aplicação Flask para upload de planilhas de medição, consulta do relatório
de calibração e gestão de pendências.

Rotas
-----

======================  ======  ===============================================
Rota                    Método  Função
======================  ======  ===============================================
``/``                   GET     Página de upload e resumo do acervo
``/importar``           POST    Processa o arquivo e mostra a **prévia**
``/confirmar``          POST    Grava a importação aprovada
``/relatorio``          GET     Relatório de calibração
``/pendencias``         GET     Lista de pendências
``/pendencias/<id>``    POST    Resolve uma pendência
``/api/medicoes``       GET     Medições em JSON
``/api/importar``       POST    Importação em JSON
``/api/estatisticas``   GET     Estatísticas do acervo em JSON
======================  ======  ===============================================

Segurança do upload
-------------------

* o formato é decidido pelos **magic bytes** do arquivo, não pela extensão;
* o tamanho é limitado por ``MAX_CONTENT_LENGTH``;
* o nome enviado pelo usuário é sanitizado e **descartado**: o arquivo é
  gravado em um diretório temporário com nome gerado (UUID);
* erros de leitura viram respostas 4xx com mensagem — nunca traceback;
* nenhum caminho de arquivo fornecido pelo usuário entra em uma consulta SQL.
"""

from __future__ import annotations

import os
import re
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Optional

from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.utils import secure_filename

from ._loader import carregar_modulo
from .etl import processar_planilha
from .leitor_planilha import (
    FormatoNaoSuportadoError,
    PlanilhaNaoReconhecidaError,
)
from .servico_importacao import ServicoImportacao

__all__ = ["criar_aplicacao", "RAIZ_PROJETO"]

#: ``04_classes`` não é importável com a instrução ``import`` porque o nome
#: começa com dígito.
classes = carregar_modulo("04_classes")

#: Raiz do projeto — a pasta que contém ``04_classes.py`` e o schema.
RAIZ_PROJETO = Path(__file__).resolve().parent.parent

#: Extensões aceitas no upload.
#:
#: ``.xls`` entra na lista mesmo sendo o formato binário legado: a
#: extensão é apenas uma dica do remetente. Quem decide é o **conteúdo**
#: (magic bytes), lido pelo :class:`LeitorPlanilha`. Aceitar a extensão
#: permite que um arquivo OOXML renomeado para ``.xls`` funcione, e faz
#: com que um ``.xls`` legítimo receba a orientação correta ("salve como
#: .xlsx") em vez de uma recusa genérica.
EXTENSOES_ACEITAS = {".xlsx", ".xlsm", ".xls"}

#: Tamanho máximo do arquivo enviado: 20 MB.
TAMANHO_MAXIMO = 20 * 1024 * 1024

#: Caracteres de controle removidos dos nomes de arquivo.
_CARACTERES_CONTROLE = re.compile(r"[\r\n\t\x00-\x1f\x7f-\x9f]")


def criar_aplicacao(caminho_banco: Optional[str] = None) -> Flask:
    """Cria e configura a aplicação Flask.

    Args:
        caminho_banco: Caminho do arquivo SQLite. Por padrão,
            ``calibracao.db`` na raiz do projeto.

    Returns:
        A aplicação configurada.
    """
    aplicacao = Flask(
        __name__,
        template_folder=str(Path(__file__).parent / "templates"),
    )
    aplicacao.config["SECRET_KEY"] = os.environ.get(
        "SCHULZ_SECRET_KEY", "schulz-av03-desenvolvimento-local"
    )
    aplicacao.config["MAX_CONTENT_LENGTH"] = TAMANHO_MAXIMO
    aplicacao.config["CAMINHO_BANCO"] = caminho_banco or str(
        RAIZ_PROJETO / "calibracao.db"
    )

    @aplicacao.context_processor
    def _variaveis_comuns() -> dict:
        return {"tem_banco": Path(aplicacao.config["CAMINHO_BANCO"]).exists()}

    @aplicacao.errorhandler(413)
    def _arquivo_grande(_erro: Any) -> Any:
        mensagem = (
            "O arquivo enviado é maior que o limite de "
            f"{TAMANHO_MAXIMO // (1024 * 1024)} MB."
        )
        if _pede_json():
            return jsonify({"ok": False, "erro": mensagem}), 413
        flash(mensagem, "erro")
        return redirect(url_for("index"))

    @aplicacao.route("/")
    def index() -> Any:
        """Página de upload com o resumo do acervo atual."""
        with _servico(aplicacao) as servico:
            resumo = servico.resumo()
            pendencias = servico.pendencias.listar_abertas()
        return render_template(
            "upload.html", resumo=resumo, pendencias=pendencias, erro=None
        )

    @aplicacao.route("/importar", methods=["POST"])
    def importar() -> Any:
        """Processa o arquivo enviado e mostra a prévia **sem gravar**.

        A gravação exige uma confirmação explícita, o que atende o fluxo
        alternativo do Caso de Uso 01 da AEx: o usuário confere os dados
        antes de eles entrarem no banco.
        """
        arquivo = request.files.get("arquivo")
        if arquivo is None or not arquivo.filename:
            mensagem = "Nenhum arquivo foi enviado."
            if _pede_json():
                return jsonify({"ok": False, "erro": mensagem}), 400
            # A página é reexibida com o status HTTP correto: um 302
            # diria "sucesso" ao cliente, o que seria falso.
            return _pagina_de_upload_com_erro(aplicacao, mensagem), 400

        extensao = Path(secure_filename(arquivo.filename)).suffix.lower()
        if extensao not in EXTENSOES_ACEITAS:
            mensagem = (
                f"Formato não aceito: {extensao or '(sem extensão)'}. "
                "Envie uma planilha Excel (.xlsx ou .xlsm)."
            )
            if _pede_json():
                return jsonify({"ok": False, "erro": mensagem}), 415
            return _pagina_de_upload_com_erro(aplicacao, mensagem), 415

        # O nome enviado pelo usuário é sanitizado e descartado: o arquivo é
        # gravado com um nome gerado, o que evita travessia de diretório.
        # O arquivo temporário sobrevive até a confirmação — a etapa de
        # confirmação reprocessa o mesmo arquivo.
        nome_temporario = os.path.join(
            tempfile.mkdtemp(prefix="schulz_upload_"), f"{uuid.uuid4().hex}{extensao}"
        )
        try:
            arquivo.save(nome_temporario)
            resultado = processar_planilha(nome_temporario)
        except FormatoNaoSuportadoError as erro:
            _remover_temporario(nome_temporario)
            mensagem = str(erro)
            if _pede_json():
                return jsonify({"ok": False, "erro": mensagem}), 415
            return _pagina_de_upload_com_erro(aplicacao, mensagem), 415
        except PlanilhaNaoReconhecidaError as erro:
            _remover_temporario(nome_temporario)
            mensagem = str(erro)
            if _pede_json():
                return jsonify({"ok": False, "erro": mensagem}), 422
            return _pagina_de_upload_com_erro(aplicacao, mensagem), 422

        resultado.arquivo = _nome_para_exibicao(arquivo.filename)

        if _pede_json():
            _remover_temporario(nome_temporario)
            return jsonify({"ok": True, "resultado": resultado.as_dict()})

        # Guarda o resultado e o caminho do temporário na sessão para a etapa
        # de confirmação. O caminho vem da sessão, **nunca** do formulário: um
        # caminho enviado pelo cliente permitiria ler arquivos arbitrários.
        anterior = session.get("previa")
        if anterior and anterior.get("caminho"):
            _remover_temporario(anterior["caminho"])
        session["previa"] = {
            "arquivo": resultado.arquivo,
            "hash": resultado.hash_arquivo,
            "aba": resultado.aba,
            "caminho": nome_temporario,
            "metadados": resultado.metadados,
            "total_registros": resultado.total_registros,
            "total_pendencias": resultado.total_pendencias,
            "blocos": resultado.blocos,
        }
        return render_template(
            "resultado_importacao.html",
            previa=session["previa"],
            resultado=resultado,
            registro=resultado.as_dict(),
        )

    @aplicacao.route("/confirmar", methods=["POST"])
    def confirmar() -> Any:
        """Grava a importação que foi pré-visualizada."""
        previa = session.get("previa")
        if not previa:
            mensagem = "Não há importação pendente de confirmação."
            if _pede_json():
                return jsonify({"ok": False, "erro": mensagem}), 400
            flash(mensagem, "erro")
            return redirect(url_for("index"))

        # O caminho vem da sessão, nunca do formulário.
        caminho = previa.get("caminho")
        if not caminho or not Path(caminho).is_file():
            mensagem = "O arquivo temporário da importação não está mais disponível."
            if _pede_json():
                return jsonify({"ok": False, "erro": mensagem}), 400
            flash(mensagem, "erro")
            return redirect(url_for("index"))

        try:
            resultado = processar_planilha(caminho)
        except (FormatoNaoSuportadoError, PlanilhaNaoReconhecidaError) as erro:
            _remover_temporario(caminho)
            session.pop("previa", None)
            mensagem = str(erro)
            if _pede_json():
                return jsonify({"ok": False, "erro": mensagem}), 400
            flash(mensagem, "erro")
            return redirect(url_for("index"))

        # O reprocessamento usa o arquivo temporário, cujo nome é um UUID.
        # A rastreabilidade (RN22) precisa do nome original, sanitizado.
        resultado.arquivo = previa.get("arquivo") or resultado.arquivo
        with _servico(aplicacao) as servico:
            gravacao = ServicoImportacao(servico).gravar(resultado)

        _remover_temporario(caminho)
        session.pop("previa", None)

        if _pede_json():
            return jsonify({"ok": True, "gravacao": gravacao.as_dict()})
        flash(
            f"Importação concluída: {gravacao.medicoes_inseridas} medição(ões) "
            f"gravada(s), {gravacao.medicoes_existentes} já existente(s), "
            f"{gravacao.pendencias_inseridas} pendência(s).",
            "sucesso",
        )
        return redirect(url_for("relatorio"))

    @aplicacao.route("/relatorio")
    def relatorio() -> Any:
        """Relatório de calibração com o JOIN de 4 tabelas."""
        with _servico(aplicacao) as servico:
            registros = servico.consultar_relatorio()
            resumo = servico.resumo()
        if _pede_json():
            return jsonify(
                {
                    "ok": True,
                    "resumo": resumo,
                    "medicoes": [dict(linha) for linha in registros],
                }
            )
        return render_template(
            "relatorio.html", registros=registros, resumo=resumo
        )

    @aplicacao.route("/pendencias")
    def pendencias() -> Any:
        """Lista as pendências em aberto."""
        with _servico(aplicacao) as servico:
            abertas = servico.pendencias.listar_abertas()
            agrupadas = servico.pendencias.agrupar_por_campo()
        if _pede_json():
            return jsonify(
                {
                    "ok": True,
                    "pendencias": [dict(linha) for linha in abertas],
                    "agrupadas": [dict(linha) for linha in agrupadas],
                }
            )
        return render_template(
            "pendencias.html", pendencias=abertas, agrupadas=agrupadas
        )

    @aplicacao.route("/pendencias/<int:id_pendencia>", methods=["POST"])
    def resolver_pendencia(id_pendencia: int) -> Any:
        """Marca uma pendência como resolvida."""
        situacao = request.form.get("situacao", "RESOLVIDA")
        if situacao not in {"RESOLVIDA", "DESCARTADA", "ABERTA"}:
            situacao = "RESOLVIDA"
        with _servico(aplicacao) as servico:
            servico.pendencias.resolver(id_pendencia, situacao)
        if _pede_json():
            return jsonify({"ok": True})
        flash(f"Pendência {id_pendencia} marcada como {situacao}.", "sucesso")
        return redirect(url_for("pendencias"))

    @aplicacao.route("/api/medicoes")
    def api_medicoes() -> Any:
        """Medições do acervo em JSON."""
        with _servico(aplicacao) as servico:
            registros = servico.consultar_relatorio()
        return jsonify({"ok": True, "medicoes": [dict(linha) for linha in registros]})

    @aplicacao.route("/api/estatisticas")
    def api_estatisticas() -> Any:
        """Estatísticas do acervo em JSON."""
        with _servico(aplicacao) as servico:
            resumo = servico.resumo()
        return jsonify({"ok": True, "resumo": resumo})

    @aplicacao.route("/api/importar", methods=["POST"])
    def api_importar() -> Any:
        """Importação direta em JSON, com gravação imediata."""
        arquivo = request.files.get("arquivo")
        if arquivo is None or not arquivo.filename:
            return jsonify({"ok": False, "erro": "nenhum arquivo enviado"}), 400

        extensao = Path(secure_filename(arquivo.filename)).suffix.lower()
        if extensao not in EXTENSOES_ACEITAS:
            return jsonify(
                {
                    "ok": False,
                    "erro": (
                        f"Formato não aceito: {extensao or '(sem extensão)'}. "
                        "Envie uma planilha Excel (.xlsx ou .xlsm)."
                    ),
                }
            ), 415

        nome_temporario = os.path.join(
            tempfile.mkdtemp(prefix="schulz_upload_"), f"{uuid.uuid4().hex}{extensao}"
        )
        try:
            arquivo.save(nome_temporario)
            resultado = processar_planilha(nome_temporario)
        except FormatoNaoSuportadoError as erro:
            return jsonify({"ok": False, "erro": str(erro)}), 415
        except PlanilhaNaoReconhecidaError as erro:
            return jsonify({"ok": False, "erro": str(erro)}), 422
        finally:
            _remover_temporario(nome_temporario)

        resultado.arquivo = _nome_para_exibicao(arquivo.filename)
        with _servico(aplicacao) as servico:
            gravacao = ServicoImportacao(servico).gravar(resultado)
        return jsonify({"ok": True, "gravacao": gravacao.as_dict()})

    return aplicacao


def _nome_para_exibicao(nome_enviado: str) -> str:
    """Normaliza o nome do arquivo enviado para exibição e rastreabilidade.

    Remove qualquer componente de caminho (``../``, ``/``, ``\\``) e
    caracteres de controle, mas **preserva os espaços**: o nome gravado em
    ``medicao.origem_arquivo`` é mostrado ao usuário e precisa continuar
    legível ("Registro MMC.xlsx", e não "Registro_MMC.xlsx").

    O nome nunca é usado como caminho em disco — o arquivo temporário recebe
    um nome gerado (UUID).
    """
    nome = str(nome_enviado or "").strip()
    nome = nome.replace("\\", "/").split("/")[-1]
    nome = _CARACTERES_CONTROLE.sub(" ", nome).strip()
    return nome or "arquivo"


def _pagina_de_upload_com_erro(aplicacao: Flask, mensagem: str):
    """Reexibe a página de upload com uma mensagem de erro.

    O status HTTP é devolvido pelo chamador: a resposta precisa refletir a
    falha, e não redirecionar como se a operação tivesse sido bem-sucedida.
    """
    with _servico(aplicacao) as servico:
        resumo = servico.resumo()
        pendencias = servico.pendencias.listar_abertas()
    return render_template(
        "upload.html", resumo=resumo, pendencias=pendencias, erro=mensagem
    )


@contextmanager
def _servico(aplicacao: Flask):
    """Abre o banco, garante o schema e entrega o serviço de orquestração.

    O schema é criado quando o arquivo ainda não existe, para que a primeira
    execução do webapp funcione sem passo manual.
    """
    classes.inicializar_banco(aplicacao.config["CAMINHO_BANCO"])
    with classes.ConexaoSQLite(aplicacao.config["CAMINHO_BANCO"]) as conexao:
        yield classes.ServicoCalibracao(conexao)


def _pede_json() -> bool:
    """Informa se a requisição espera uma resposta JSON."""
    if request.path.startswith("/api/"):
        return True
    return request.accept_mimetypes.best == "application/json"


def _remover_temporario(caminho: str) -> None:
    """Remove o arquivo temporário e o diretório que o contém."""
    try:
        Path(caminho).unlink(missing_ok=True)
        Path(caminho).parent.rmdir()
    except OSError:
        pass
