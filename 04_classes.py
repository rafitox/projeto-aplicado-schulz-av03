"""Classes de domínio, conexão e persistência do MVP de calibração (Schulz S.A.).

Entrega 03 (AV03) do Projeto Aplicado I. Este módulo concentra:

* as entidades de domínio ``Tecnico``, ``Equipamento``, ``Padrao`` e ``Medicao``;
* a regra de negócio metrológica (média, desvio, desvio-padrão e o veredito
  ``APROVADO``/``REPROVADO``);
* a camada de persistência sobre SQLite (``ConexaoSQLite`` + repositórios);
* o serviço de orquestração (``ServicoCalibracao``).

Regras estruturais do projeto:

* Este módulo importa **apenas a biblioteca padrão** — nada de ``schulz_mvp``.
* Todo acesso ao banco usa parâmetros (``?``). Nunca há concatenação de SQL.
* A aritmética de tolerância é feita em ``decimal.Decimal``. A conversão partindo
  do ``float`` do banco é feita por ``Decimal(str(x))``, e não por
  ``Decimal(x)``, que embutiria o erro binário do ponto flutuante.
* ``PRAGMA foreign_keys = ON`` é aplicado em **toda** conexão, porque o SQLite o
  associa à conexão e não o persiste no arquivo.
"""

from __future__ import annotations

import sqlite3
import statistics
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional, Sequence

__all__ = [
    # Exceções
    "CalibracaoError",
    "ValidacaoError",
    "RegraMetrologicaError",
    "PersistenciaError",
    "RegistroDuplicadoError",
    "ReferenciaInvalidaError",
    "PendenciaAbertaError",
    # Entidades
    "Tecnico",
    "Equipamento",
    "Padrao",
    "Medicao",
    # Persistência
    "ConexaoSQLite",
    "RepositorioBase",
    "TecnicoRepositorio",
    "EquipamentoRepositorio",
    "PadraoRepositorio",
    "MedicaoRepositorio",
    "PendenciaRepositorio",
    "HistoricoRepositorio",
    # Serviço
    "ServicoCalibracao",
    # Utilitários
    "STATUS_APROVADO",
    "STATUS_REPROVADO",
    "para_decimal",
    "inicializar_banco",
]

STATUS_APROVADO = "APROVADO"
STATUS_REPROVADO = "REPROVADO"


# ===========================================================================
# EXCEÇÕES
# ===========================================================================


class CalibracaoError(Exception):
    """Base de todos os erros lançados pelo sistema de calibração."""


class ValidacaoError(CalibracaoError):
    """Dados ausentes, malformados ou incoerentes (RN04, RN06, RN19)."""


class RegraMetrologicaError(CalibracaoError):
    """Critério técnico de metrologia não aplicável ao registro (RN11, RN24)."""


class PersistenciaError(CalibracaoError):
    """Falha de banco encapsulada. A exceção original fica em ``__cause__``."""


class RegistroDuplicadoError(PersistenciaError):
    """Violação de restrição UNIQUE (RN21)."""


class ReferenciaInvalidaError(PersistenciaError):
    """Violação de FOREIGN KEY (RN02, RN18)."""


class PendenciaAbertaError(CalibracaoError):
    """Operação bloqueada por pendência em aberto (RN13)."""


# ===========================================================================
# UTILITÁRIOS
# ===========================================================================


def para_decimal(valor: Any) -> Optional[Decimal]:
    """Converte um valor para ``Decimal`` sem embutir erro binário de ``float``.

    ``Decimal(0.1)`` guarda o valor binário exato de ``0.1`` e produz
    ``0.1000000000000000055511151231257827``. ``Decimal(str(0.1))`` parte da
    representação decimal pretendida. A diferença é observável na fronteira
    de tolerância: ``0.1 + 0.2 <= 0.3`` é ``False`` em ``float`` e ``True``
    em ``Decimal``.

    Retorna ``None`` quando o valor é ``None`` ou não é numérico.
    """
    if valor is None:
        return None
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, bool):
        raise ValidacaoError(f"valor booleano não é numérico: {valor!r}")
    try:
        return Decimal(str(valor).strip().replace(",", "."))
    except (InvalidOperation, ValueError, AttributeError) as erro:
        raise ValidacaoError(f"valor não numérico: {valor!r}") from erro


def _texto(valor: Any) -> Optional[str]:
    """Normaliza um valor para texto, removendo espaços nas pontas."""
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto or None


def _validar_data_iso(valor: str, campo: str) -> None:
    """Valida uma data no formato ``AAAA-MM-DD`` (RN04)."""
    try:
        datetime.strptime(valor, "%Y-%m-%d")
    except ValueError as erro:
        raise ValidacaoError(
            f"{campo} inválido: {valor!r}. Esperado no formato AAAA-MM-DD"
        ) from erro


def _validar_hora(valor: Optional[str], campo: str) -> None:
    """Valida um horário no formato ``HH:MM:SS`` (RN04)."""
    if valor is None:
        return
    try:
        datetime.strptime(valor, "%H:%M:%S")
    except ValueError as erro:
        raise ValidacaoError(
            f"{campo} inválido: {valor!r}. Esperado no formato HH:MM:SS"
        ) from erro


# ===========================================================================
# ENTIDADES
# ===========================================================================


@dataclass
class Tecnico:
    """Profissional responsável pela medição ou pela solicitação do processo.

    O atributo chamador é ``matricula``, conforme o roteiro da AV03
    ("Classe Tecnico: ... `id_tecnico`, `matricula`, `nome`, `setor`"). A
    coluna correspondente no banco chama-se ``codigo``, nome herdado da
    Entrega 02; a tradução fica em :meth:`to_row` e :meth:`from_row`, e o
    alias ``codigo`` continua disponível em Python.
    """

    nome: str
    matricula: str
    setor: Optional[str] = None
    id_tecnico: Optional[int] = None

    def __post_init__(self) -> None:
        self.validar()

    def validar(self) -> None:
        """Verifica os campos obrigatórios do cadastro (RN04, RN06)."""
        if not _texto(self.nome):
            raise ValidacaoError("nome do técnico é obrigatório")
        if not _texto(self.matricula):
            raise ValidacaoError("matrícula do técnico é obrigatória")

    @property
    def codigo(self) -> str:
        """Alias de :attr:`matricula`, com o nome da coluna no banco."""
        return self.matricula

    def to_row(self) -> dict:
        """Converte a entidade em dicionário pronto para o ``INSERT``."""
        return {
            "nome": self.nome,
            "codigo": self.matricula,
            "setor": self.setor,
        }

    @classmethod
    def from_row(cls, linha: Any) -> "Tecnico":
        """Constrói a entidade a partir de uma linha do banco."""
        return cls(
            nome=linha["nome"],
            matricula=linha["codigo"],
            setor=linha["setor"],
            id_tecnico=linha["id_tecnico"],
        )


@dataclass
class Equipamento:
    """Instrumento de medição utilizado no processo.

    Os atributos chamadores são ``codigo_tag`` e ``descricao``, conforme o
    roteiro da AV03 ("Classe Equipamento: ... `codigo_tag`, `descricao`,
    `fabricante`"). As colunas no banco chamam-se ``codigo`` e ``nome``,
    nomes herdados da Entrega 02; a tradução fica em :meth:`to_row` e
    :meth:`from_row`, e os aliases ``codigo`` e ``nome`` continuam
    disponíveis em Python.
    """

    codigo_tag: str
    descricao: str
    fabricante: Optional[str] = None
    modelo: Optional[str] = None
    numero_serie: Optional[str] = None
    id_equipamento: Optional[int] = None

    def __post_init__(self) -> None:
        self.validar()

    def validar(self) -> None:
        """Verifica os campos obrigatórios do cadastro (RN04, RN06)."""
        if not _texto(self.codigo_tag):
            raise ValidacaoError("código TAG do equipamento é obrigatório")
        if not _texto(self.descricao):
            raise ValidacaoError("descrição do equipamento é obrigatória")

    @property
    def codigo(self) -> str:
        """Alias de :attr:`codigo_tag`, com o nome da coluna no banco."""
        return self.codigo_tag

    @property
    def nome(self) -> str:
        """Alias de :attr:`descricao`, com o nome da coluna no banco."""
        return self.descricao

    def to_row(self) -> dict:
        """Converte a entidade em dicionário pronto para o ``INSERT``."""
        return {
            "codigo": self.codigo_tag,
            "nome": self.descricao,
            "fabricante": self.fabricante,
            "modelo": self.modelo,
            "numero_serie": self.numero_serie,
        }

    @classmethod
    def from_row(cls, linha: Any) -> "Equipamento":
        """Constrói a entidade a partir de uma linha do banco."""
        return cls(
            codigo_tag=linha["codigo"],
            descricao=linha["nome"],
            fabricante=linha["fabricante"],
            modelo=linha["modelo"],
            numero_serie=linha["numero_serie"],
            id_equipamento=linha["id_equipamento"],
        )


@dataclass
class Padrao:
    """Padrão de medição (instrumento de referência) usado na calibração.

    Vinculá-lo à medição é o que sustenta a rastreabilidade metrológica
    exigida pelo INMETRO e formalizada na regra RN18.
    """

    codigo: str
    modelo: str
    fabricante: Optional[str] = None
    numero_serie: Optional[str] = None
    ultima_calibracao: Optional[str] = None
    proxima_calibracao: Optional[str] = None
    certificado_padrao: Optional[str] = None
    id_padrao: Optional[int] = None

    def __post_init__(self) -> None:
        self.validar()

    def validar(self) -> None:
        """Verifica os campos obrigatórios do padrão (RN04, RN18)."""
        if not _texto(self.codigo):
            raise ValidacaoError("código do padrão é obrigatório")
        if not _texto(self.modelo):
            raise ValidacaoError("modelo do padrão é obrigatório")
        if self.ultima_calibracao is not None:
            _validar_data_iso(self.ultima_calibracao, "ultima_calibracao")
        if self.proxima_calibracao is not None:
            _validar_data_iso(self.proxima_calibracao, "proxima_calibracao")

    def to_row(self) -> dict:
        """Converte a entidade em dicionário pronto para o ``INSERT``."""
        return {
            "codigo": self.codigo,
            "modelo": self.modelo,
            "fabricante": self.fabricante,
            "numero_serie": self.numero_serie,
            "ultima_calibracao": self.ultima_calibracao,
            "proxima_calibracao": self.proxima_calibracao,
            "certificado_padrao": self.certificado_padrao,
        }

    @classmethod
    def from_row(cls, linha: Any) -> "Padrao":
        """Constrói a entidade a partir de uma linha do banco."""
        return cls(
            codigo=linha["codigo"],
            modelo=linha["modelo"],
            fabricante=linha["fabricante"],
            numero_serie=linha["numero_serie"],
            ultima_calibracao=linha["ultima_calibracao"],
            proxima_calibracao=linha["proxima_calibracao"],
            certificado_padrao=linha["certificado_padrao"],
            id_padrao=linha["id_padrao"],
        )


@dataclass
class Medicao:
    """Ensaio de calibração, com a regra de veredito de tolerância encapsulada."""

    id_tecnico: int
    id_equipamento: int
    caracteristica: str
    valor_nominal: float
    tol_inferior: float
    tol_superior: float
    valor_obtido: float
    unidade: str
    data_medicao: str
    id_padrao: Optional[int] = None
    id_medicao: Optional[int] = None
    ordem_servico: Optional[str] = None
    plano_medicao: Optional[str] = None
    hora_medicao: Optional[str] = None
    desenho: Optional[str] = None
    peca: Optional[str] = None
    medida_1: Optional[float] = None
    medida_2: Optional[float] = None
    bloco: int = 1
    origem_arquivo: Optional[str] = None
    origem_linha: Optional[int] = None
    origem_hash: Optional[str] = None
    certificado_numero: Optional[str] = None
    usuario_aprovacao: Optional[str] = None
    data_aprovacao: Optional[str] = None
    certificado_data: Optional[str] = None

    def __post_init__(self) -> None:
        self.validar()

    # -- validação ---------------------------------------------------------

    def validar(self) -> None:
        """Verifica a coerência do ensaio (RN04, RN06, RN07).

        As tolerâncias são simétricas por convenção: ``tol_inferior`` é negativa
        e ``tol_superior`` é positiva. A regra preserva o sinal original — o
        valor não é normalizado com ``abs()`` (RN07).
        """
        if not _texto(self.caracteristica):
            raise ValidacaoError("característica é obrigatória")
        if not _texto(self.unidade):
            raise ValidacaoError("unidade de medida é obrigatória")
        if not _texto(self.data_medicao):
            raise ValidacaoError("data da medição é obrigatória")
        _validar_data_iso(self.data_medicao, "data_medicao")
        _validar_hora(self.hora_medicao, "hora_medicao")
        if self.id_tecnico is None:
            raise ValidacaoError("técnico responsável é obrigatório")
        if self.id_equipamento is None:
            raise ValidacaoError("equipamento utilizado é obrigatório")
        para_decimal(self.valor_nominal)
        para_decimal(self.valor_obtido)
        para_decimal(self.tol_inferior)
        para_decimal(self.tol_superior)
        if para_decimal(self.tol_inferior) > para_decimal(self.tol_superior):
            raise ValidacaoError(
                "tolerância invertida: tol_inferior não pode ser maior que "
                "tol_superior"
            )
        if self.bloco is not None and int(self.bloco) < 1:
            raise ValidacaoError("bloco deve ser um inteiro maior ou igual a 1")

    # -- grandezas calculadas --------------------------------------------

    def limite_inferior(self) -> Decimal:
        """Limite inferior de aceitação: ``valor_nominal + tol_inferior`` (RN11)."""
        return para_decimal(self.valor_nominal) + para_decimal(self.tol_inferior)

    def limite_superior(self) -> Decimal:
        """Limite superior de aceitação: ``valor_nominal + tol_superior`` (RN11)."""
        return para_decimal(self.valor_nominal) + para_decimal(self.tol_superior)

    def media(self) -> Optional[Decimal]:
        """Média das medidas válidas (RN09).

        Medidas ausentes (``None``) são ignoradas — não contam como zero.
        Retorna ``None`` quando não há nenhuma medida.
        """
        medidas = [
            valor
            for valor in (para_decimal(self.medida_1), para_decimal(self.medida_2))
            if valor is not None
        ]
        if not medidas:
            return None
        return sum(medidas) / Decimal(len(medidas))

    def desvio(self) -> Decimal:
        """Desvio do resultado em relação ao valor nominal (RN10)."""
        return para_decimal(self.valor_obtido) - para_decimal(self.valor_nominal)

    def desvio_padrao(self) -> Optional[Decimal]:
        """Desvio-padrão amostral das medidas (n-1, correção de Bessel).

        Exige ao menos duas medidas; com menos, retorna ``None``. É a
        convenção metrológica para dispersão de medições repetidas.
        """
        medidas = [
            valor
            for valor in (para_decimal(self.medida_1), para_decimal(self.medida_2))
            if valor is not None
        ]
        if len(medidas) < 2:
            return None
        return para_decimal(statistics.stdev(medidas))

    # -- veredito ----------------------------------------------------------

    def avaliar(self) -> str:
        """Determina o situação do resultado frente às tolerâncias (RN11).

        O intervalo é **inclusivo**: um resultado exatamente sobre o limite é
        considerado aprovado. A comparação é feita em ``Decimal`` para evitar
        erro de representação na fronteira.
        """
        if self.limite_inferior() <= para_decimal(self.valor_obtido) <= self.limite_superior():
            return STATUS_APROVADO
        return STATUS_REPROVADO

    def status_resultado(self) -> str:
        """Situação do resultado: ``APROVADO`` ou ``REPROVADO``."""
        return self.avaliar()

    # -- persistência ------------------------------------------------------

    def to_row(self) -> dict:
        """Converte a entidade em dicionário pronto para o ``INSERT``."""
        media = self.media()
        desvio_padrao = self.desvio_padrao()
        return {
            "id_tecnico": self.id_tecnico,
            "id_equipamento": self.id_equipamento,
            "id_padrao": self.id_padrao,
            "ordem_servico": self.ordem_servico,
            "plano_medicao": self.plano_medicao,
            "data_medicao": self.data_medicao,
            "hora_medicao": self.hora_medicao,
            "desenho": self.desenho,
            "peca": self.peca,
            "caracteristica": self.caracteristica,
            "valor_nominal": float(self.valor_nominal),
            "tol_superior": float(self.tol_superior),
            "tol_inferior": float(self.tol_inferior),
            "medida_1": self.medida_1,
            "medida_2": self.medida_2,
            "media": float(media) if media is not None else None,
            "desvio_padrao": float(desvio_padrao) if desvio_padrao is not None else None,
            "valor_obtido": float(self.valor_obtido),
            "desvio": float(self.desvio()),
            "unidade": self.unidade,
            "status_resultado": self.avaliar(),
            "certificado_numero": self.certificado_numero,
            "usuario_aprovacao": self.usuario_aprovacao,
            "data_aprovacao": self.data_aprovacao,
            "certificado_data": self.certificado_data,
            "origem_arquivo": self.origem_arquivo,
            "origem_linha": self.origem_linha,
            "origem_hash": self.origem_hash,
            "bloco": self.bloco,
        }

    @classmethod
    def from_row(cls, linha: Any) -> "Medicao":
        """Constrói a entidade a partir de uma linha do banco."""
        return cls(
            id_tecnico=linha["id_tecnico"],
            id_equipamento=linha["id_equipamento"],
            caracteristica=linha["caracteristica"],
            valor_nominal=linha["valor_nominal"],
            tol_inferior=linha["tol_inferior"],
            tol_superior=linha["tol_superior"],
            valor_obtido=linha["valor_obtido"],
            unidade=linha["unidade"],
            data_medicao=linha["data_medicao"],
            id_padrao=linha["id_padrao"],
            id_medicao=linha["id_medicao"],
            ordem_servico=linha["ordem_servico"],
            plano_medicao=linha["plano_medicao"],
            hora_medicao=linha["hora_medicao"],
            desenho=linha["desenho"],
            peca=linha["peca"],
            medida_1=linha["medida_1"],
            medida_2=linha["medida_2"],
            bloco=linha["bloco"] if "bloco" in linha.keys() else 1,
            origem_arquivo=linha["origem_arquivo"] if "origem_arquivo" in linha.keys() else None,
            origem_linha=linha["origem_linha"] if "origem_linha" in linha.keys() else None,
            origem_hash=linha["origem_hash"] if "origem_hash" in linha.keys() else None,
            certificado_numero=linha["certificado_numero"],
            usuario_aprovacao=linha["usuario_aprovacao"],
            data_aprovacao=linha["data_aprovacao"],
            certificado_data=linha["certificado_data"] if "certificado_data" in linha.keys() else None,
        )


# ===========================================================================
# CONEXÃO
# ===========================================================================


class ConexaoSQLite:
    """Gerencia a conexão com o SQLite e a tradução de erros do driver.

    O ``PRAGMA foreign_keys`` é aplicado na entrada do gerenciador de contexto
    porque o SQLite o associa à conexão — ele não é persistido no arquivo.
    Uma conexão aberta sem esse ``PRAGMA`` aceita gravações que violam as
    chaves estrangeiras sem qualquer aviso.
    """

    def __init__(self, caminho: Any, criar_schema: bool = False) -> None:
        self.caminho = str(caminho)
        self.criar_schema = criar_schema
        self._conexao: Optional[sqlite3.Connection] = None

    # -- ciclo de vida -----------------------------------------------------

    @property
    def connection(self) -> sqlite3.Connection:
        """A conexão ``sqlite3`` crua. Use para operações fora da API do repositório."""
        return self._exigir_conexao()

    def __enter__(self) -> "ConexaoSQLite":
        """Abre a conexão e devolve o próprio gerenciador.

        O gerenciador — e não a conexão crua — é o que se passa aos
        repositórios, porque é ele quem traduz os erros do driver para a
        hierarquia de exceções do domínio. A conexão ``sqlite3`` crua fica
        disponível pelo atributo ``connection``.
        """
        self._conexao = sqlite3.connect(self.caminho)
        self._conexao.execute("PRAGMA foreign_keys = ON")
        self._conexao.row_factory = sqlite3.Row
        if self.criar_schema:
            self.criar_esquema()
        return self

    def __exit__(self, tipo_exc: Any, valor_exc: Any, tb: Any) -> None:
        if self._conexao is not None:
            try:
                if tipo_exc is None:
                    self._conexao.commit()
                else:
                    self._conexao.rollback()
            finally:
                self._conexao.close()
                self._conexao = None

    # -- execução ----------------------------------------------------------

    def executar(self, sql: str, params: Sequence = ()) -> sqlite3.Cursor:
        """Executa um comando SQL parametrizado."""
        conexao = self._exigir_conexao()
        try:
            return conexao.execute(sql, params)
        except sqlite3.Error as erro:
            raise _traduzir_erro(erro) from erro

    def consultar(self, sql: str, params: Sequence = ()) -> list:
        """Executa uma consulta parametrizada e devolve todas as linhas."""
        conexao = self._exigir_conexao()
        try:
            return list(conexao.execute(sql, params).fetchall())
        except sqlite3.Error as erro:
            raise _traduzir_erro(erro) from erro

    @contextmanager
    def em_transacao(self) -> Iterator[sqlite3.Connection]:
        """Agrupa operações em uma transação: confirma no sucesso, desfaz no erro.

        Sem transação explícita, uma falha no meio de um lote de inserções
        deixa as gravações anteriores persistidas.

        O agrupamento usa ``SAVEPOINT`` e não ``BEGIN``: o SAVEPOINT desfaz
        **apenas** o que foi feito dentro do bloco, preservando o que já
        estava gravado antes dele. Um ``ROLLBACK`` comum desfaria a transação
        inteira, incluindo o trabalho anterior ao bloco.
        """
        conexao = self._exigir_conexao()
        # Nome interno, gerado pelo código — nunca vem do usuário.
        nome_savepoint = f"savepoint_{uuid.uuid4().hex}"
        try:
            conexao.execute(f"SAVEPOINT {nome_savepoint}")
        except sqlite3.Error as erro:
            raise _traduzir_erro(erro) from erro
        try:
            yield conexao
        except Exception:
            try:
                conexao.execute(f"ROLLBACK TO SAVEPOINT {nome_savepoint}")
                conexao.execute(f"RELEASE SAVEPOINT {nome_savepoint}")
            except sqlite3.Error:
                pass
            raise
        else:
            try:
                conexao.execute(f"RELEASE SAVEPOINT {nome_savepoint}")
            except sqlite3.Error as erro:
                raise _traduzir_erro(erro) from erro

    # -- esquema -----------------------------------------------------------

    def criar_esquema(self) -> None:
        """Cria o schema v3 a partir de ``03_banco.sql``."""
        from pathlib import Path

        caminho_sql = Path(__file__).with_name("03_banco.sql")
        if not caminho_sql.exists():
            raise PersistenciaError(f"script de schema não encontrado: {caminho_sql}")
        conexao = self._exigir_conexao()
        try:
            conexao.executescript(caminho_sql.read_text(encoding="utf-8"))
        except sqlite3.Error as erro:
            raise _traduzir_erro(erro) from erro
        conexao.commit()

    # -- interno -----------------------------------------------------------

    def _exigir_conexao(self) -> sqlite3.Connection:
        if self._conexao is None:
            raise PersistenciaError(
                "conexão não está aberta: use 'with ConexaoSQLite(...) as conexao:'"
            )
        return self._conexao


def inicializar_banco(caminho: Any) -> bool:
    """Garante que o banco exista e tenha o schema v3.

    Cria o arquivo e as tabelas quando ainda não existem. Um arquivo já
    existente com o schema da Entrega 02 é preservado — a evolução para o
    schema v3 é feita pelo script ``03b_migracao.sql``.

    Args:
        caminho: Caminho do arquivo SQLite.

    Returns:
        ``True`` se o schema foi criado nesta chamada.
    """
    caminho = Path(caminho)
    precisa_criar = not caminho.exists()

    if not precisa_criar:
        with ConexaoSQLite(caminho) as conexao:
            tabelas = {
                linha[0]
                for linha in conexao.consultar(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            precisa_criar = "medicao" not in tabelas

    if precisa_criar:
        with ConexaoSQLite(caminho, criar_schema=True):
            pass
        return True
    return False


def _traduzir_erro(erro: sqlite3.Error) -> PersistenciaError:
    """Traduz um erro do driver SQLite para a hierarquia de exceções do domínio.

    ``sqlite3.Error`` nunca escapa da camada de persistência: quem consome o
    repositório trabalha apenas com as exceções de domínio.
    """
    mensagem = str(erro)
    if isinstance(erro, sqlite3.IntegrityError):
        if "FOREIGN KEY" in mensagem:
            return ReferenciaInvalidaError(
                f"violação de chave estrangeira: {mensagem}"
            )
        if "UNIQUE" in mensagem:
            return RegistroDuplicadoError(f"registro duplicado: {mensagem}")
        if "CHECK" in mensagem:
            return ValidacaoError(f"violação de restrição: {mensagem}")
        return PersistenciaError(f"erro de integridade: {mensagem}")
    return PersistenciaError(f"erro de banco de dados: {mensagem}")


# ===========================================================================
# REPOSITÓRIOS
# ===========================================================================


class RepositorioBase:
    """Base comum dos repositórios: guarda a conexão e expõe o cursor."""

    tabela = ""

    def __init__(self, conexao: ConexaoSQLite) -> None:
        self.conexao = conexao

    def _inserir(self, sql: str, valores: dict) -> int:
        colunas = list(valores)
        marcadores = ", ".join("?" for _ in colunas)
        cursor = self.conexao.executar(
            f"INSERT INTO {self.tabela} ({', '.join(colunas)}) VALUES ({marcadores})",
            tuple(valores[coluna] for coluna in colunas),
        )
        return int(cursor.lastrowid)

    def _atualizar(self, sql: str, valores: dict) -> int:
        colunas = list(valores)
        atribuicoes = ", ".join(f"{coluna} = ?" for coluna in colunas)
        cursor = self.conexao.executar(
            f"UPDATE {self.tabela} SET {atribuicoes} WHERE id = ?",
            tuple(valores[coluna] for coluna in colunas) + (valores["id"],),
        )
        return cursor.rowcount


class TecnicoRepositorio(RepositorioBase):
    """Persistência dos técnicos e solicitantes."""

    tabela = "tecnico_solicitante"

    def inserir(self, tecnico: Tecnico) -> int:
        """Insere um técnico e devolve o identificador gerado."""
        return self._inserir(
            "INSERT INTO tecnico_solicitante (nome, codigo, setor) VALUES (?, ?, ?)",
            tecnico.to_row(),
        )

    def listar(self) -> list:
        """Devolve todos os técnicos cadastrados."""
        return self.conexao.consultar(
            "SELECT * FROM tecnico_solicitante ORDER BY nome"
        )

    def buscar_por_codigo(self, codigo: str) -> Optional[Tecnico]:
        """Localiza um técnico pelo código (matrícula)."""
        linhas = self.conexao.consultar(
            "SELECT * FROM tecnico_solicitante WHERE codigo = ?", (codigo,)
        )
        return Tecnico.from_row(linhas[0]) if linhas else None

    def buscar_por_id(self, id_tecnico: int) -> Optional[Tecnico]:
        """Localiza um técnico pelo identificador."""
        linhas = self.conexao.consultar(
            "SELECT * FROM tecnico_solicitante WHERE id_tecnico = ?", (id_tecnico,)
        )
        return Tecnico.from_row(linhas[0]) if linhas else None


class EquipamentoRepositorio(RepositorioBase):
    """Persistência dos equipamentos (instrumentos de medição)."""

    tabela = "equipamento"

    def inserir(self, equipamento: Equipamento) -> int:
        """Insere um equipamento e devolve o identificador gerado."""
        return self._inserir(
            "INSERT INTO equipamento (codigo, nome, fabricante, modelo, numero_serie) "
            "VALUES (?, ?, ?, ?, ?)",
            equipamento.to_row(),
        )

    def listar(self) -> list:
        """Devolve todos os equipamentos cadastrados."""
        return self.conexao.consultar("SELECT * FROM equipamento ORDER BY nome")

    def buscar_por_codigo(self, codigo: str) -> Optional[Equipamento]:
        """Localiza um equipamento pelo código (TAG)."""
        linhas = self.conexao.consultar(
            "SELECT * FROM equipamento WHERE codigo = ?", (codigo,)
        )
        return Equipamento.from_row(linhas[0]) if linhas else None


class PadraoRepositorio(RepositorioBase):
    """Persistência dos padrões de medição."""

    tabela = "padrao"

    def inserir(self, padrao: Padrao) -> int:
        """Insere um padrão e devolve o identificador gerado."""
        return self._inserir(
            "INSERT INTO padrao (codigo, modelo, fabricante, numero_serie, "
            "ultima_calibracao, proxima_calibracao, certificado_padrao) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            padrao.to_row(),
        )

    def listar(self) -> list:
        """Devolve todos os padrões cadastrados."""
        return self.conexao.consultar("SELECT * FROM padrao ORDER BY codigo")

    def buscar_por_codigo(self, codigo: str) -> Optional[Padrao]:
        """Localiza um padrão pelo código."""
        linhas = self.conexao.consultar(
            "SELECT * FROM padrao WHERE codigo = ?", (codigo,)
        )
        return Padrao.from_row(linhas[0]) if linhas else None

    def calibracao_vencida(self, data_referencia: str) -> list:
        """Padrões cuja próxima calibração já passou (RN18)."""
        return self.conexao.consultar(
            "SELECT * FROM padrao WHERE proxima_calibracao IS NOT NULL "
            "AND proxima_calibracao < ? ORDER BY proxima_calibracao",
            (data_referencia,),
        )


class MedicaoRepositorio(RepositorioBase):
    """Persistência das medições."""

    tabela = "medicao"

    _COLUNAS = (
        "id_tecnico, id_equipamento, id_padrao, ordem_servico, plano_medicao, "
        "data_medicao, hora_medicao, desenho, peca, caracteristica, valor_nominal, "
        "tol_superior, tol_inferior, medida_1, medida_2, media, desvio_padrao, "
        "valor_obtido, desvio, unidade, status_resultado, certificado_numero, "
        "usuario_aprovacao, data_aprovacao, certificado_data, origem_arquivo, "
        "origem_linha, origem_hash, bloco"
    )

    def inserir(self, medicao: Medicao) -> int:
        """Insere uma medição e devolve o identificador gerado."""
        valores = medicao.to_row()
        colunas = list(valores)
        marcadores = ", ".join("?" for _ in colunas)
        cursor = self.conexao.executar(
            f"INSERT INTO medicao ({', '.join(colunas)}) VALUES ({marcadores})",
            tuple(valores[coluna] for coluna in colunas),
        )
        return int(cursor.lastrowid)

    def listar(self) -> list:
        """Devolve todas as medições."""
        return self.conexao.consultar("SELECT * FROM medicao ORDER BY id_medicao")

    def buscar_por_id(self, id_medicao: int) -> Optional[Medicao]:
        """Localiza uma medição pelo identificador."""
        linhas = self.conexao.consultar(
            "SELECT * FROM medicao WHERE id_medicao = ?", (id_medicao,)
        )
        return Medicao.from_row(linhas[0]) if linhas else None

    def listar_relatorio(self) -> list:
        """Relatório relacional com técnico, equipamento e padrão (JOIN de 4 tabelas)."""
        return self.conexao.consultar(
            """
            SELECT
                m.id_medicao,
                t.nome AS tecnico,
                t.codigo AS matricula,
                e.codigo AS equipamento,
                e.nome AS equipamento_nome,
                p.codigo AS padrao,
                m.ordem_servico,
                m.caracteristica,
                m.valor_nominal,
                m.valor_obtido,
                m.desvio,
                m.desvio_padrao,
                m.unidade,
                m.status_resultado,
                m.certificado_numero,
                m.data_medicao
            FROM medicao AS m
            INNER JOIN tecnico_solicitante AS t
                ON m.id_tecnico = t.id_tecnico
            INNER JOIN equipamento AS e
                ON m.id_equipamento = e.id_equipamento
            LEFT JOIN padrao AS p
                ON m.id_padrao = p.id_padrao
            ORDER BY m.id_medicao
            """
        )

    def contar_por_tecnico(self) -> list:
        """Quantidade de medições por técnico, incluindo quem não mediu."""
        return self.conexao.consultar(
            """
            SELECT t.nome AS tecnico, COUNT(m.id_medicao) AS quantidade_medicoes
            FROM tecnico_solicitante AS t
            LEFT JOIN medicao AS m
                ON t.id_tecnico = m.id_tecnico
            GROUP BY t.id_tecnico, t.nome
            ORDER BY t.nome
            """
        )

    def listar_reprovadas(self) -> list:
        """Medições reprovadas, com técnico e equipamento."""
        return self.conexao.consultar(
            """
            SELECT m.id_medicao, t.nome AS tecnico, e.codigo AS equipamento,
                   m.caracteristica, m.valor_nominal, m.valor_obtido,
                   m.desvio, m.unidade, m.status_resultado
            FROM medicao AS m
            INNER JOIN tecnico_solicitante AS t
                ON m.id_tecnico = t.id_tecnico
            INNER JOIN equipamento AS e
                ON m.id_equipamento = e.id_equipamento
            WHERE m.status_resultado = 'REPROVADO'
            ORDER BY m.id_medicao
            """
        )

    def listar_por_origem(self, origem_hash: str) -> list:
        """Medições originadas de um arquivo específico (RN22)."""
        return self.conexao.consultar(
            "SELECT * FROM medicao WHERE origem_hash = ? ORDER BY origem_linha",
            (origem_hash,),
        )

    def ja_importado(self, origem_hash: str, origem_linha: int) -> bool:
        """Informa se a linha de origem já foi importada (RN21)."""
        linhas = self.conexao.consultar(
            "SELECT 1 FROM medicao WHERE origem_hash = ? AND origem_linha = ? LIMIT 1",
            (origem_hash, origem_linha),
        )
        return bool(linhas)

    def registrar_aprovacao(
        self,
        id_medicao: int,
        usuario: str,
        data_aprovacao: str,
        certificado_numero: str,
        certificado_data: Optional[str] = None,
    ) -> None:
        """Grava a aprovação técnica e a identificação do certificado (RN14/RN15/RN16)."""
        self.conexao.executar(
            """
            UPDATE medicao
            SET usuario_aprovacao = ?, data_aprovacao = ?,
                certificado_numero = ?, certificado_data = ?
            WHERE id_medicao = ?
            """,
            (usuario, data_aprovacao, certificado_numero, certificado_data, id_medicao),
        )


class PendenciaRepositorio(RepositorioBase):
    """Persistência das pendências de correção (RN13/RN19/RN20)."""

    tabela = "pendencia"

    def registrar(
        self,
        campo: str,
        descricao: str,
        criticidade: str = "MEDIA",
        id_medicao: Optional[int] = None,
        id_tecnico: Optional[int] = None,
        origem_arquivo: Optional[str] = None,
        status: str = "ABERTA",
    ) -> int:
        """Registra uma pendência e devolve o identificador gerado."""
        return self._inserir(
            """
            INSERT INTO pendencia (id_medicao, id_tecnico, origem_arquivo, campo,
                                    descricao, criticidade, status, data_registro)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            {
                "id_medicao": id_medicao,
                "id_tecnico": id_tecnico,
                "origem_arquivo": origem_arquivo,
                "campo": campo,
                "descricao": descricao,
                "criticidade": criticidade,
                "status": status,
                "data_registro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
        )

    def listar_abertas(self) -> list:
        """Pendências em aberto, da mais crítica para a menos crítica."""
        return self.conexao.consultar(
            """
            SELECT * FROM pendencia
            WHERE status = 'ABERTA'
            ORDER BY CASE criticidade
                WHEN 'ALTA' THEN 1 WHEN 'MEDIA' THEN 2 ELSE 3 END,
                data_registro DESC
            """
        )

    def agrupar_por_campo(self) -> list:
        """Pendências abertas agrupadas pelo campo de origem."""
        return self.conexao.consultar(
            """
            SELECT campo, COUNT(*) AS quantidade, MAX(criticidade) AS criticidade
            FROM pendencia
            WHERE status = 'ABERTA'
            GROUP BY campo
            ORDER BY quantidade DESC
            """
        )

    def resolver(self, id_pendencia: int, status: str = "RESOLVIDA") -> None:
        """Marca a pendência como resolvida ou descartada."""
        self.conexao.executar(
            """
            UPDATE pendencia
            SET status = ?, data_resolucao = ?
            WHERE id_pendencia = ?
            """,
            (status, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), id_pendencia),
        )

    def contar_abertas_por_medicao(self, id_medicao: int) -> int:
        """Quantidade de pendências em aberto de uma medição (RN13)."""
        linhas = self.conexao.consultar(
            "SELECT COUNT(*) FROM pendencia WHERE id_medicao = ? AND status = 'ABERTA'",
            (id_medicao,),
        )
        return int(linhas[0][0]) if linhas else 0


class HistoricoRepositorio(RepositorioBase):
    """Persistência da trilha de auditoria (RF15/RNF03/RN17)."""

    tabela = "historico"

    def registrar(
        self,
        acao: str,
        usuario: Optional[str] = None,
        id_medicao: Optional[int] = None,
        detalhe: Optional[str] = None,
    ) -> int:
        """Registra uma ação no histórico e devolve o identificador gerado."""
        return self._inserir(
            """
            INSERT INTO historico (id_medicao, acao, usuario, data_hora, detalhe)
            VALUES (?, ?, ?, ?, ?)
            """,
            {
                "id_medicao": id_medicao,
                "acao": acao,
                "usuario": usuario,
                "data_hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "detalhe": detalhe,
            },
        )

    def listar_todos(self) -> list:
        """Todo o histórico, do mais recente para o mais antigo."""
        return self.conexao.consultar(
            "SELECT * FROM historico ORDER BY id_historico DESC"
        )

    def listar_por_medicao(self, id_medicao: int) -> list:
        """Histórico de uma medição, do mais recente para o mais antigo."""
        return self.conexao.consultar(
            "SELECT * FROM historico WHERE id_medicao = ? ORDER BY id_historico DESC",
            (id_medicao,),
        )

    def listar_por_usuario(self, usuario: str) -> list:
        """Histórico das ações de um usuário."""
        return self.conexao.consultar(
            "SELECT * FROM historico WHERE usuario = ? ORDER BY id_historico DESC",
            (usuario,),
        )


# ===========================================================================
# SERVIÇO
# ===========================================================================


class ServicoCalibracao:
    """Orquestra as regras de negócio sobre os repositórios.

    É a camada que a interface (terminal ou webapp) chama. Ela não conhece
    SQL: apenas os repositórios.
    """

    def __init__(self, conexao: ConexaoSQLite) -> None:
        self.conexao = conexao
        self.tecnicos = TecnicoRepositorio(conexao)
        self.equipamentos = EquipamentoRepositorio(conexao)
        self.padroes = PadraoRepositorio(conexao)
        self.medicoes = MedicaoRepositorio(conexao)
        self.pendencias = PendenciaRepositorio(conexao)
        self.historico = HistoricoRepositorio(conexao)

    # -- cadastros ---------------------------------------------------------

    def registrar_tecnico(self, tecnico: Tecnico) -> int:
        """Cadastra um técnico. Reutiliza o cadastro se o código já existir."""
        existente = self.tecnicos.buscar_por_codigo(tecnico.codigo)
        if existente is not None:
            return existente.id_tecnico
        return self.tecnicos.inserir(tecnico)

    def registrar_equipamento(self, equipamento: Equipamento) -> int:
        """Cadastra um equipamento. Reutiliza o cadastro se o código já existir."""
        existente = self.equipamentos.buscar_por_codigo(equipamento.codigo)
        if existente is not None:
            return existente.id_equipamento
        return self.equipamentos.inserir(equipamento)

    def registrar_padrao(self, padrao: Padrao) -> int:
        """Cadastra um padrão de medição. Reutiliza o cadastro se já existir."""
        existente = self.padroes.buscar_por_codigo(padrao.codigo)
        if existente is not None:
            return existente.id_padrao
        return self.padroes.inserir(padrao)

    # -- medições ----------------------------------------------------------

    def registrar_medicao(self, medicao: Medicao) -> int:
        """Registra uma medição calculando média, desvio e situação (RN09/RN10/RN11).

        A gravação e o registro no histórico acontecem na mesma transação: ou
        os dois ocurren, ou nenhum.
        """
        with self.conexao.em_transacao():
            id_medicao = self.medicoes.inserir(medicao)
            self.historico.registrar(
                acao="MEDICAO_REGISTRADA",
                id_medicao=id_medicao,
                detalhe=(
                    f"{medicao.caracteristica}: {medicao.avaliar()} "
                    f"({medicao.valor_obtido} {medicao.unidade})"
                ),
            )
        return id_medicao

    def registrar_pendencia(
        self,
        campo: str,
        descricao: str,
        criticidade: str = "MEDIA",
        id_medicao: Optional[int] = None,
        id_tecnico: Optional[int] = None,
        origem_arquivo: Optional[str] = None,
    ) -> int:
        """Registra uma pendência de correção e a registra no histórico (RN19/RN20)."""
        with self.conexao.em_transacao():
            id_pendencia = self.pendencias.registrar(
                campo=campo,
                descricao=descricao,
                criticidade=criticidade,
                id_medicao=id_medicao,
                id_tecnico=id_tecnico,
                origem_arquivo=origem_arquivo,
            )
            self.historico.registrar(
                acao="PENDENCIA_REGISTRADA",
                id_medicao=id_medicao,
                detalhe=f"{campo}: {descricao}",
            )
        return id_pendencia

    def aprovar_medicao(
        self,
        id_medicao: int,
        usuario: str,
        certificado_numero: str,
        data_aprovacao: Optional[str] = None,
    ) -> Medicao:
        """Aprova tecnicamente a medição e registra o certificado (RN13–RN17).

        Uma medição com pendência em aberto **não** pode ser aprovada: o
        registro permanece bloqueado até a correção (RN13).
        """
        pendencias = self.pendencias.contar_abertas_por_medicao(id_medicao)
        if pendencias > 0:
            raise PendenciaAbertaError(
                f"a medição {id_medicao} possui {pendencias} pendência(s) em aberto "
                "e não pode ser aprovada"
            )
        medicao = self.medicoes.buscar_por_id(id_medicao)
        if medicao is None:
            raise ValidacaoError(f"medição {id_medicao} não encontrada")

        agora = datetime.now()
        data_aprovacao = data_aprovacao or agora.strftime("%Y-%m-%d")
        with self.conexao.em_transacao():
            self.medicoes.registrar_aprovacao(
                id_medicao=id_medicao,
                usuario=usuario,
                data_aprovacao=data_aprovacao,
                certificado_numero=certificado_numero,
                certificado_data=agora.strftime("%Y-%m-%d"),
            )
            self.historico.registrar(
                acao="CERTIFICADO_EMITIDO",
                usuario=usuario,
                id_medicao=id_medicao,
                detalhe=f"certificado {certificado_numero}",
            )
        return self.medicoes.buscar_por_id(id_medicao)

    # -- consultas ---------------------------------------------------------

    def consultar_relatorio(self) -> list:
        """Relatório de calibração com técnico, equipamento e padrão."""
        return self.medicoes.listar_relatorio()

    def resumo(self) -> dict:
        """Resumo quantitativo do acervo para o relatório do terminal."""
        total = len(self.medicoes.listar())
        aprovados = len(
            self.conexao.consultar(
                "SELECT 1 FROM medicao WHERE status_resultado = 'APROVADO'"
            )
        )
        reprovados = len(self.medicoes.listar_reprovadas())
        pendencias = len(self.pendencias.listar_abertas())
        return {
            "total": total,
            "aprovados": aprovados,
            "reprovados": reprovados,
            "pendencias": pendencias,
        }
