# 06 — Documentação Técnica do MVP (Parte 1)

**Projeto Aplicado I — Entrega 03 (AV03)**
**Empresa parceira:** Schulz S.A.
**Escopo:** Classes de domínio em Programação Orientada a Objetos, conexão com banco relacional SQLite e importação de planilhas de medição
**Linguagem:** Python 3.8+

---

## 1. Contextualização

Nas entregas anteriores (AV01 e AV02) a equipe investigou os
processos manuais da Schulz S.A., levantou os requisitos operacionais e as
regras de negócio, e modelou o banco de dados relacional em SQLite com três
tabelas: `tecnicos`, `equipamentos` e `medicoes`.

A AV03 é a passagem **do modelo para o código**. O objetivo central é
implementar a arquitetura em POO, construindo as classes de domínio, os
objetos de acesso a dados e os algoritmos de validação das regras
metrológicas sobre o SQLite.

Este documento descreve o MVP entregue: as decisões de arquitetura, os
padrões de POO aplicados, a diagramação das classes, o tratamento de erros
SQL, a importação de planilhas e a validação do fluxo funcional.

### 1.1 O que o MVP entrega

| Item do roteiro | Entrega |
|---|---|
| 1. Classes de domínio e conexão SQL (`04_classes.py`) | `04_classes.py` |
| 2. Script principal de demonstração (`05_main.py`) | `05_main.py` |
| 3. Documentação técnica do MVP — Parte 1 (`06_mvp_parte1.md`) | este documento |

A entrega acrescenta, além do escopo mínimo, um **webapp de upload de
planilhas** que executa o mesmo ETL já aplicado na disciplina de Big Data.
A justificativa está na seção 7.

---

## 2. Decisões de arquitetura

### 2.1 Por que Python e não Java

O roteiro aceita as duas linguagens. A escolha foi Python por três razões
concretas:

1. **O módulo `sqlite3` é da biblioteca padrão.** O roteiro exige conexão
   com SQLite "via JDBC em Java ou `sqlite3` em Python". Em Java isso exige
   uma dependência externa (`org.xerial:sqlite-jdbc`) e um gerenciador de
   dependências (Maven/Gradle) para que o avaliador consiga executar o
   projeto. Em Python, `import sqlite3` já resolve.
2. **Continuidade com a Entrega 02**, cujo script (`sistema.py`) já estava em
   Python e já implementava o CRUD sobre o mesmo schema.
3. **A regra metrológica é Expressiva em Python.** O veredito
   APROVADO/REPROVADO é uma comparação de intervalos, e `decimal.Decimal`
   — parte da biblioteca padrão — dá a exatidão necessária na fronteira
   (seção 2.5).

### 2.2 Estrutura de pastas e regra de dependência

O roteiro exige arquivos com nomes prefixados (`04_classes.py`,
`05_main.py`, `06_mvp_parte1.md`). Um nome que começa com dígito **não é um
identificador Python válido**: `import 04_classes` é um `SyntaxError`
("invalid decimal literal").

A solução adotada mantém os nomes literais exigidos e usa um carregador por
caminho:

```python
# schulz_mvp/_loader.py
especificacao = importlib.util.spec_from_file_location(nome_arquivo, caminho)
modulo = importlib.util.module_from_spec(especificacao)
sys.modules[nome_arquivo] = modulo          # <- antes de exec_module
especificacao.loader.exec_module(modulo)
```

O registro em `sys.modules` **precisa** ocorrer antes da execução do
arquivo: as anotações de tipo do `dataclass` resolvem o módulo de origem da
classe por esse dicionário enquanto o arquivo ainda está sendo executado.

A organização final separa o que é genuinamente separável:

```
projeto_aplicado_3/
+-- 04_classes.py            <- implementacao: entidades, conexao, repositorios, servico
+-- 05_main.py               <- script de demonstracao
+-- 07_webapp.py             <- ponto de entrada do webapp
+-- schulz_mvp/
|   +-- _loader.py           <- carrega modulos com prefixo numerico
|   +-- leitor_planilha.py    <- leitor Excel (openpyxl + fallback stdlib)
|   +-- etl.py               <- ETL puro (sem Flask, sem banco)
|   +-- servico_importacao.py<- ETL -> SQLite em transacao
|   +-- relatorio.py         <- relatorio no terminal
|   +-- webapp.py            <- Flask: rotas e upload multipart
|   +-- templates/           <- Jinja2
+-- tests/
```

A **regra de dependência é unidirecional**:

```
webapp.py -> servico_importacao.py -> etl.py -> leitor_planilha.py
                                                        |
                                                 04_classes.py
                                                        |
                                                     stdlib
```

`04_classes.py` **nunca** importa o pacote `schulz_mvp`. Isso não é
estetismo: mantém o núcleo do roteiro testável e executável sem Flask e sem
`openpyxl` instalados, e garante que o ETL possa ser reusado fora do webapp.

### 2.3 Separação de responsabilidades

Cada camada tem uma responsabilidade única e não conhece a anterior:

| Camada | Responsabilidade | Não sabe |
|---|---|---|
| `leitor_planilha.py` | ler Excel e devolver uma grade de células | o formato MMC, o banco, o Flask |
| `etl.py` | extrair, sanear e validar os dados | o banco, o Flask, SQL |
| `servico_importacao.py` | gravar o resultado do ETL | a planilha, o Flask |
| `04_classes.py` | domínio, regra de negócio e persistência | planilhas, Flask, web |
| `webapp.py` | receber o arquivo, orquestrar, renderizar | SQL, regra metrológica |

### 2.4 Por que `Decimal` e não `float`

A comparação de tolerância acontece exatamente na fronteira do limite
aceitável, e é justamente ali que a representação binária de ponto
flutuante erra:

```python
>>> 0.1 + 0.2 <= 0.3
False            # float: o resultado e 0.30000000000000004
>>> Decimal("0.1") + Decimal("0.2") <= Decimal("0.3")
True             # Decimal: a aritmetica e decimal, nao binaria
```

Uma peça medida exatamente no limite seria **reprovada** pela comparação em
`float` e **aprovada** pela comparação em `Decimal`. O mesmo vale para a
conversão: `Decimal(0.1)` guarda o valor binário exato de `0.1`
(`0.1000000000000000055511151231257827`), enquanto `Decimal(str(0.1))` parte
da representação decimal pretendida. Por isso toda conversão usa
`Decimal(str(x))`, e nunca `Decimal(float)`.

O SQLite não possui tipo decimal exato: o valor é armazenado como `REAL` e
a exatidão é recovering no momento do cálculo, em Python.

### 2.5 Por que `unittest` e não `pytest`

O roteiro informa que o projeto deve rodar com "apenas Python 3 instalado".
`pytest` não faz parte da biblioteca padrão e não está instalado no
ambiente de avaliação. `unittest` é da biblioteca padrão e atende a todos os
casos. Os testes escritos em `unittest` também rodam sob `pytest`, caso o
avaliador o prefira — não há perda de portabilidade.

### 2.6 O que o SQLite garante e o que não garante

O `PRAGMA foreign_keys` **não** é persistido no arquivo de banco: ele vale
**por conexão**. Uma aplicação que abre o banco e esquece de ligá-lo aceita
gravações que violam as chaves estrangeiras sem qualquer aviso. Por isso o
`ConexaoSQLite` liga o PRAGMA na entrada do gerenciador de contexto, e
`04_classes.py` nunca abre uma conexão SQLite por fora dele.

Há um segundo detalhe: no SQLite, valores `NULL` são considerados **distintos**
em índices `UNIQUE`. Uma restrição de unicidade que contenha uma coluna
normalmente nula não impede duplicatas. Isso influenciou diretamente o
desenho da chave de idempotência da importação (seção 7.5).

---

## 3. Modelagem POO

### 3.1 Padrões aplicados

| Padrão | Onde aparece | Para quê |
|---|---|---|
| **Encapsulamento** | `@property`, `@dataclass`, validação em `__post_init__` | O estado do objeto é sempre válido: nasce validado ou não nasce |
| **Classe de dados (Data Class)** | `Tecnico`, `Equipamento`, `Padrao`, `Medicao` | Structs com validação, `to_row()`/`from_row()` e semântica de valor |
| **Imutabilidade relativa** | `@dataclass(frozen=False)` + atributos privados de derivação | O estado muda por operação explícita (`avaliar()`), nunca por efeito colateral |
| **Herança** | Hierarquia de exceções | `CalibracaoError` como base; erros de persistência se especializam |
| **Composição** | `ServicoCalibracao` → repositórios → `ConexaoSQLite` | O serviço compõe o que ele usa, em vez de herdar |
| **Repository / DAO** | `TecnicoRepositorio`, `MedicaoRepositorio`, … | O acesso a dados fica isolado; a regra de negócio não vê SQL |
| **Service Layer** | `ServicoCalibracao` | Regras de orquestração (registrar, aprovar, emitir) fora das entidades |
| **Adapter** | `LeitorPlanilha` | Isola o formato Excel atrás de uma interface estável |
| **Facade** | `schulz_mvp/_loader.py` | Esconde o detalhe do carregamento por prefixo numérico |
| **Strategy parametrizada** | `Medicao.avaliar()` com tolerâncias como dados | RN24: nenhuma constante mágica de tolerância espalhada no código |
| **Value Object** | `Decimal` para grandezas metrológicas | Semântica de valor exato para comparação de limites |
| **Repository + Unit of Work** | `ConexaoSQLite.em_transacao()` com `SAVEPOINT` | Agrupa gravações e desfaz o lote sem afetar o que veio antes |

### 3.2 Diagrama de classes

```
+-----------------------------------------------------------------------+
|                           CalibracaoError                              |
|                            (excecao base)                              |
+-----------------------------------------------------------------------+
        ^            ^              ^                 ^
        |            |              |                 |
+----------+  +--------------+  +--------------+  +---------------+
| Valida   |  | RegraMetro   |  | Persistencia |  | Pendencia     |
| caoError |  | logicaError  |  |    Error     |  | AbertaError   |
+----------+  +--------------+  +--------------+  +---------------+
                                      ^        ^
                          +-----------+        +-----------+
                          |                       |
              +---------------+        +---------------------+
              |RegistroDuplicado|       |ReferenciaInvalida   |
              |     Error      |       |       Error         |
              +---------------+        +---------------------+


+-------------------------------------------------------------------------+
|                              Tecnico                                   |
+-------------------------------------------------------------------------+
| - nome         : str                                                 |
| - matricula    : str          <- roteiro AV03 ("matricula")            |
| - setor        : str?                                                 |
| - id_tecnico   : int?                                                |
+-------------------------------------------------------------------------+
| + matricula -> str          (atributo)                                |
| + codigo     -> str          (alias do nome da coluna)                |
| + validar()                                                        |
| + to_row() / from_row()                                             |
+-------------------------------------------------------------------------+
         ^                                    ^
         | 1                                 N |
         |                                    |
+--------+-------------------------------------+---------+
|                Medicao                              |
+-------------------------------------------------------+
| - id_tecnico      : int   (obrigatorio)              |
| - id_equipamento  : int   (obrigatorio)              |
| - id_padrao       : int?  (opcional: rastreabilidade)|
| - caracteristica  : str   (obrigatorio)              |
| - valor_nominal   : float                           |
| - tol_inferior    : float   (negativo por convencao)|
| - tol_superior    : float                           |
| - valor_obtido    : float                           |
| - unidade         : str    (obrigatorio)              |
| - data_medicao    : str    (AAAA-MM-DD)              |
| - medida_1, medida_2, media, desvio_padrao : float?  |
| - bloco           : int = 1                         |
| - origem_arquivo, origem_linha, origem_hash : str?   |
| - certificado_numero, usuario_aprovacao, ... : str?  |
+-------------------------------------------------------+
| + limite_inferior() -> Decimal                        |
| + limite_superior() -> Decimal                        |
| + media()           -> Decimal?                       |
| + desvio()          -> Decimal                        |
| + desvio_padrao()   -> Decimal?                       |
| + avaliar()         -> 'APROVADO' | 'REPROVADO'      |
| + status_resultado()-> 'APROVADO' | 'REPROVADO'      |
| + validar()                                             |
+-------------------------------------------------------+


+-------------------------------------------------------------------------+
|                            Equipamento                                 |
+-------------------------------------------------------------------------+
| - codigo_tag   : str          <- roteiro AV03 ("codigo_tag")           |
| - descricao    : str          <- roteiro AV03 ("descricao")            |
| - fabricante   : str?                                               |
| - modelo       : str?                                               |
| - numero_serie : str?                                               |
| - id_equipamento: int?                                              |
+-------------------------------------------------------------------------+
| + codigo -> str          (alias do nome da coluna)                    |
| + nome   -> str          (alias do nome da coluna)                    |
| + validar() / to_row() / from_row()                                  |
+-------------------------------------------------------------------------+


+-------------------------------------------------------------------------+
|                              Padrao                                    |
+-------------------------------------------------------------------------+
| - codigo, modelo : str (obrigatorios)                                 |
| - fabricante, numero_serie : str?                                    |
| - ultima_calibracao, proxima_calibracao : str? (AAAA-MM-DD)           |
| - certificado_padrao : str?                                          |
| - id_padrao : int?                                                   |
+-------------------------------------------------------------------------+


+-------------------------------------------------------------------------+
|                         ConexaoSQLite                                 |
+-------------------------------------------------------------------------+
| - caminho : str                                                      |
| - criar_schema : bool                                                |
+-------------------------------------------------------------------------+
| + __enter__() -> ConexaoSQLite   (PRAGMA foreign_keys = ON)          |
| + __exit__()                     (commit / rollback / close)         |
| + executar(sql, params) -> Cursor                                     |
| + consultar(sql, params) -> list[Row]                                 |
| + em_transacao() -> ContextManager  (SAVEPOINT)                       |
| + criar_esquema()                                                   |
+-------------------------------------------------------------------------+
            ^
            | 1 (composicao)
            |
+-------------------------------------------------------------------------+
|                        ServicoCalibracao                              |
+-------------------------------------------------------------------------+
| - conexao : ConexaoSQLite                                           |
+-------------------------------------------------------------------------+
| + registrar_tecnico(t) -> int                                         |
| + registrar_equipamento(e) -> int                                     |
| + registrar_padrao(p) -> int                                          |
| + registrar_medicao(m) -> int                                         |
| + registrar_pendencia(...) -> int                                     |
| + aprovar_medicao(id, usuario, certificado) -> Medicao                 |
| + consultar_relatorio() -> list[Row]                                  |
| + resumo() -> dict                                                    |
+-------------------------------------------------------------------------+
   |         |          |          |          |
   v         v          v          v          v
+------+ +--------+ +--------+ +--------+ +--------+
|Tecnico| |Equipam.| |Padrao | |Medicao| |Penden.|
|Repo   | |Repo    | |Repo   | |Repo   | |Hist.  |
+------+ +--------+ +--------+ +--------+ +--------+
   \         |          |          |         /
    \________|__________|__________|________/
                    ConexaoSQLite
```

### 3.3 Vocabulário: o roteiro e o banco

O roteiro da AV03 nomeia os atributos das classes de uma forma
(`matricula`, `codigo_tag`, `descricao`), e o schema do banco usa outra
(`codigo`, `nome`), herdada da Entrega 02. A AEx, por sua vez, fala em
"código" ao longo do texto.

Resolver isso apagando um dos dois vocabulários trairia alguém. A solução
adoptada é: **a entidade segue o roteiro** (é ela que a avaliação da POO
lê), **a coluna segue o banco** (é ela que não obriga a migrar o banco já
entregue), e a tradução fica isolada em `to_row()`/`from_row()`.

| Entidade (roteiro) | Coluna (banco) | Alias em Python |
|---|---|---|
| `Tecnico.matricula` | `tecnico_solicitante.codigo` | `Tecnico.codigo` |
| `Equipamento.codigo_tag` | `equipamento.codigo` | `Equipamento.codigo` |
| `Equipamento.descricao` | `equipamento.nome` | `Equipamento.nome` |

Quem já conhece a Entrega 02 continua usando `codigo` e `nome` sem breakage;
quem segue o roteiro encontra `matricula`, `codigo_tag` e `descricao`.

### 3.4 Diagrama de sequência — registro e aprovação

```
Usuario     ServicoCalibracao    MedicaoRepositorio   Medicao      Historico
   |                |                    |               |            |
   | registrar_medicao(medicao)          |               |            |
   |--------------->|                    |               |            |
   |                | medicao.avaliar()  |               |            |
   |                |----------------------------------------> |       |
   |                |<----------------------------------------|       |
   |                | (APROVADO / REPROVADO)                   |       |
   |                |                    |               |            |
   |                | INSERT medicao    |               |            |
   |                |------------------->|               |            |
   |                |<-------------------|               |            |
   |                | id_medicao        |               |            |
   |                |                    |               |            |
   |                | INSERT historico ('MEDICAO_REGISTRADA')        |
   |                |----------------------------------------->|       |
   |                |                    |               |            |
   |                |<-- SAVEPOINT liberado, transacao confirmada    |
   |<---------------| id_medicao        |               |            |
   |                |                    |               |            |
   | aprovar_medicao(id, usuario, cert)  |               |            |
   |--------------->|                    |               |            |
   |                | pendencias abertas para a medicao?             |
   |                |---------------------------------------------->|    |
   |                |<----------------------------------------------|    |
   |                | (0 pendencias -> segue; >0 -> PendenciaAbertaError)
   |                |                    |               |            |
   |                | UPDATE medicao (certificado, aprovacao)         |
   |                |------------------->|               |            |
   |                |                    |               |            |
   |                | INSERT historico ('CERTIFICADO_EMITIDO')        |
   |                |----------------------------------------->|       |
   |                |                    |               |            |
   |<---------------| Medicao atualizada  |               |            |
```

### 3.5 Hierarquia de exceções

```
Exception
   |
   +-- CalibracaoError ................ base de todos os erros do sistema
         |
         +-- ValidacaoError .......... dado ausente, malformado ou incoerente
         |                              (RN04, RN06, RN19, violacao de CHECK)
         |
         +-- RegraMetrologicaError ... criterio tecnico nao aplicavel
         |                              (RN11, RN24)
         |
         +-- PendenciaAbertaError .... operacao bloqueada por pendencia
         |                              em aberto (RN13)
         |
         +-- PersistenciaError ........ falha de banco encapsulada
               |
               +-- RegistroDuplicadoError ... violacao de UNIQUE (RN21)
               |
               +-- ReferenciaInvalidaError .. violacao de FOREIGN KEY
                                              (RN02, RN18)
```

`sqlite3.Error` **nunca** escapa da camada de persistência: a função
`_traduzir_erro` o converte na hierarquia acima, e a exceção original fica
em `__cause__`, preservando a rastreabilidade do erro.

### 3.6 Onde cada padrão aparece, em código

**Encapsulamento e validação na construção.** Uma entidade nasce válida ou
não nasce:

```python
@dataclass
class Medicao:
    # ...
    def __post_init__(self) -> None:
        self.validar()
```

**Regra parametrizada, sem constante mágica (RN24).** As tolerâncias são
dados, não código:

```python
def limite_inferior(self) -> Decimal:
    """Limite inferior: valor_nominal + tol_inferior (RN11)."""
    return para_decimal(self.valor_nominal) + para_decimal(self.tol_inferior)
```

**Repository isolando o SQL.** A regra de negócio não contém uma única
string SQL:

```python
def buscar_por_codigo(self, codigo: str) -> Optional[Tecnico]:
    linhas = self.conexao.consultar(
        "SELECT * FROM tecnico_solicitante WHERE codigo = ?", (codigo,)
    )
    return Tecnico.from_row(linhas[0]) if linhas else None
```

**Service Layer orquestrando.** `ServicoCalibracao` decide, as entidades
calculam, os repositórios persistem:

```python
def registrar_medicao(self, medicao: Medicao) -> int:
    with self.conexao.em_transacao():
        id_medicao = self.medicoes.inserir(medicao)
        self.historico.registrar(
            acao="MEDICAO_REGISTRADA",
            id_medicao=id_medicao,
            detalhe=(...),
        )
    return id_medicao
```

---

## 4. Persistência e tratamento de erros SQL

### 4.1 O gerenciador de conexão

`ConexaoSQLite` é um gerenciador de contexto. Ele aplica o `PRAGMA
foreign_keys = ON` na abertura, porque o SQLite associa essa configuração à
conexão e não a persiste no arquivo — uma conexão aberta sem o PRAGMA
aceitaria gravações que violam as chaves estrangeiras sem qualquer aviso.

```python
def __enter__(self) -> "ConexaoSQLite":
    self._conexao = sqlite3.connect(self.caminho)
    self._conexao.execute("PRAGMA foreign_keys = ON")
    self._conexao.row_factory = sqlite3.Row
    if self.criar_schema:
        self.criar_esquema()
    return self
```

Duas escolhas merecem registro:

- O contexto devolve **o próprio gerenciador**, e não a conexão crua. É o
  gerenciador quem traduz os erros do driver para a hierarquia de exceções
  do domínio; a conexão `sqlite3` crua fica disponível pelo atributo
  `connection`, para quem precisar.
- `row_factory = sqlite3.Row` permite acessar as colunas por nome
  (`linha["nome"]`) e convertê-las com `dict(linha)`.

### 4.2 Uso obrigatório de parâmetros

Todo acesso ao banco usa parâmetros (`?`). Não há concatenação de string em
SQL em nenhum ponto do código — inclusive nos `INSERT`, onde os nomes das
colunas vêm de uma lista interna e os valores vão por parâmetro:

```python
def _inserir(self, sql: str, valores: dict) -> int:
    colunas = list(valores)
    marcadores = ", ".join("?" for _ in colunas)
    cursor = self.conexao.executar(
        f"INSERT INTO {self.tabela} ({', '.join(colunas)}) VALUES ({marcadores})",
        tuple(valores[coluna] for coluna in colunas),
    )
    return int(cursor.lastrowid)
```

A f-string monta apenas **nomes de coluna**, que são conhecidos pelo código; os
**valores** — a parte que vem de fora — sempre são parâmetros. O teste
`test_sql_injection_e_tratado` confirma que uma string de injeção enviada
como valor é tratada como dado.

### 4.3 Tradução de erros do driver

A função `_traduzir_erro` é a fronteira entre o driver e o domínio:

| Erro do `sqlite3` | Significado | Exceção do domínio | Requisito |
|---|---|---|---|
| `IntegrityError` com `FOREIGN KEY` | chave estrangeira inexistente | `ReferenciaInvalidaError` | RN02, RN18 |
| `IntegrityError` com `UNIQUE` | violação de unicidade | `RegistroDuplicadoError` | RN21 |
| `IntegrityError` com `CHECK` | valor fora do domínio permitido | `ValidacaoError` | RN04, RN11 |
| `IntegrityError` (outro) | violação de integridade | `PersistenciaError` | — |
| `OperationalError` / outros | falha genérica de banco | `PersistenciaError` | — |

O `sqlite3.Error` original fica em `__cause__` (a palavra-chave `raise ...
from erro`), de modo que a pilha de chamadas completa permanece disponível
para depuração.

### 4.4 Transações: `SAVEPOINT`, não `BEGIN`

O `em_transacao()` usa `SAVEPOINT` em vez de `BEGIN`/`ROLLBACK`. A
diferença importa:

- um `ROLLBACK` comum **desfaz a transação inteira**, inclusive o que já
  tinha sido gravado antes do bloco — o lote anterior desapareceria junto;
- um `SAVEPOINT` desfaz **apenas** o que foi feito dentro do bloco,
  preservando o que veio antes.

```python
@contextmanager
def em_transacao(self) -> Iterator[sqlite3.Connection]:
    conexao = self._exigir_conexao()
    nome_savepoint = f"savepoint_{uuid.uuid4().hex}"
    conexao.execute(f"SAVEPOINT {nome_savepoint}")
    try:
        yield conexao
    except Exception:
        conexao.execute(f"ROLLBACK TO SAVEPOINT {nome_savepoint}")
        conexao.execute(f"RELEASE SAVEPOINT {nome_savepoint}")
        raise
    else:
        conexao.execute(f"RELEASE SAVEPOINT {nome_savepoint}")
```

O nome do savepoint é gerado pelo código (`uuid4`), nunca vem do usuário.

Esse detalhe foi encontrado por um teste: a primeira versão usava
`ROLLBACK`, e o teste `test_transacao_desfaz_em_erro` reprovou porque a
inserção feita **antes** do bloco também tinha sido desfeita.

### 4.5 Integridade referencial verificada em execução

`PRAGMA foreign_key_check` sobre o banco gerado:

```
$ sqlite3 calibracao.db "PRAGMA foreign_key_check;"
```

**Resultado: nenhuma linha.** Nenhuma violação de integridade referencial.

A consulta 6 de `03c_testes.sql` faz a mesma verificação por JOIN, e a
consulta 18 repete o `PRAGMA` — ambas devem devolver zero linhas.

---

## 5. Regras de negócio implementadas

### 5.1 Regras de negócio (RN)

| RN | Regra | Onde está implementada |
| --- | ----- | ---------------------- |
| RN01 | PK `AUTOINCREMENT` em todas as tabelas | `03_banco.sql` |
| RN02 | `medicao.id_tecnico` e `id_equipamento` `NOT NULL` com FK | `03_banco.sql` |
| RN04 | Data `AAAA-MM-DD`, hora `HH:MM:SS` | `Medicao.validar()` + `CHECK` no schema |
| RN06 | Valores numéricos válidos | `para_decimal()` |
| RN07 | Tolerâncias preservam o sinal | `Medicao.validar()`, ETL |
| RN08 | Unidade preservada, sem conversão | `Medicao.unidade` |
| RN09 | `media()` = média das medidas não nulas | `Medicao.media()` |
| RN10 | `desvio()` = obtido - nominal | `Medicao.desvio()` |
| RN11 | `avaliar()` → APROVADO / REPROVADO (intervalo inclusivo) | `Medicao.avaliar()` |
| RN13 | Aprovação bloqueada por pendência em aberto | `ServicoCalibracao.aprovar_medicao()` |
| RN14 | Usuário e data de aprovação gravados | `MedicaoRepositorio.registrar_aprovacao()` |
| RN15 | Número de certificado único | `UNIQUE` em `certificado_numero` |
| RN16 | Data de emissão do certificado | `medicao.certificado_data` |
| RN17 | Toda ação relevante vira histórico | `HistoricoRepositorio` |
| RN18 | Padrão de medição vinculado | tabela `padrao` + FK |
| RN19 | Campo ausente vira pendência `ABERTA` | `ServicoCalibracao.registrar_pendencia()` |
| RN20 | Erro de importação fica registrado | `pendencia.origem_arquivo` |
| RN21 | Controle de duplicidade | `UNIQUE (origem_hash, origem_linha)` |
| RN22 | Origem dos dados preservada | `origem_arquivo`, `origem_linha`, `origem_hash` |
| RN24 | Limites como parâmetro, sem constante mágica | `Medicao.avaliar()` |



**Testes que verificam cada regra**

- **RN01** — `TestIntegridadeReferencial`
- **RN02** — `test_tecnico_inexistente_e_barrado`, `test_equipamento_inexistente_e_barrado`
- **RN04** — `test_data_invalida_rejeitada`, `test_hora_invalida_rejeitada`
- **RN06** — `test_texto_nao_numerico_levanta_erro`
- **RN07** — `test_sinal_das_tolerancias_preservado`
- **RN08** — `test_unidade_obrigatoria`
- **RN09** — `test_media_das_duas_medidas`, `test_media_ignora_medida_ausente`
- **RN10** — `test_desvio_e_a_diferenca_para_o_nominal`
- **RN11** — `test_exatamente_no_limite_superior_aprovado`, `test_fronteira_decimal_nao_sofre_erro_de_float`
- **RN13** — `test_aprovacao_bloqueada_por_pendencia`
- **RN14** — `test_aprovacao_grava_certificado`
- **RN15** — `03c_testes.sql`
- **RN16** — `test_aprovacao_grava_certificado`
- **RN17** — `test_historico_registra_as_acoes`
- **RN18** — `test_relatorio_traz_JOIN_de_4_tabelas`
- **RN19** — `test_aprovacao_bloqueada_por_pendencia`
- **RN20** — `test_pendencias_agrupadas_por_campo`
- **RN21** — `test_mesma_origem_e_linha_e_barrada`, `test_reimportacao_nao_duplica`
- **RN22** — `test_confirmacao_grava_a_origem`
- **RN24** — `test_limites_soma_as_tolerancias`
### 5.2 Requisitos funcionais (RF) cobertos

| RF | Requisito | Implementação |
| --- | --------- | ------------- |
| RF01 | Importar dados de medição | `LeitorPlanilha` + `etl.py` + `POST /importar` |
| RF02 | Identificar informações do arquivo | `etl.py` lê as células de metadados |
| RF03 | Ler os resultados da medição | `etl.py` lê Actual/Nominal/Tolerâncias/Desvio |
| RF04 | Cadastrar e consultar instrumentos | `Equipamento` + repositório |
| RF05 | Consultar MMC, responsáveis e fornecedores | `Tecnico`, `Equipamento` + relatório |
| RF06 | Relacionar medição, equipamento e responsável | FKs + `ServicoCalibracao` |
| RF07 | Validar campos obrigatórios | `etl.py` gera pendência; prévia antes de gravar |
| RF08 | Calcular a média das medições | `Medicao.media()` |
| RF09 | Calcular o desvio | `Medicao.desvio()` |
| RF11 | Iniciar o processamento consolidado | `ServicoCalibracao.registrar_medicao()` |
| RF14 | Consultar registros com filtros | `GET /relatorio`, `GET /api/medicoes` |
| RF15 | Manter histórico das ações | tabela `historico` |



**Verificação de cada requisito**

- **RF01** — upload da planilha real → 28 registros na prévia
- **RF02** — `plano == "703.1208_TESTE"`, `data == "2026-08-13"`
- **RF03** — 28 registros com os 5 campos
- **RF04** — `test_persistencia.py`
- **RF05** — `test_relatorio_traz_JOIN_de_4_tabelas`
- **RF06** — `test_tecnico_inexistente_e_barrado`
- **RF07** — `test_previa_nao_grava_no_banco`
- **RF08** — `test_media_das_duas_medidas`
- **RF09** — `test_desvio_e_a_diferenca_para_o_nominal`
- **RF11** — `test_historico_registra_as_acoes`
- **RF14** — `test_api_de_medicoes_devolve_28_registros`
- **RF15** — `test_historico_registra_as_acoes`
**Fora do escopo desta parte** (declarado como limitação na seção 10):
RF10 (incerteza), RF12 e RF13 (emissão do certificado em PDF).

---

## 6. Validação do fluxo funcional

### 6.1 Caso de uso 1 — Importar arquivo de medição

**Comportamento no MVP:** o usuário envia a planilha pela interface web. O
sistema extrai os dados, identifica a aba de medições pelo cabeçalho,
segmenta os blocos de medição, sanear os valores, e **apresenta tudo para
conferência antes de gravar**. Só após a confirmação as medições são
persistidas.

**Saída real** da prévia sobre `Registro MMC.xlsx` (extraída da página
renderizada):

```
Medições extraídas

 Linha  Bloco  Característica    Nominal   Obtido     Tol. sup.  Tol. inf.
  14     1      PLANICIDADE_REF   0         0.002167   0.05       0
  15     1      ENTRE CENTROS_REF 0         0.0274147  0.04       0
  16     1      62P_DIÂMETRO 1     6.075     6.0787295  0.01      -0.01
  ...
  29     2      PLANICIDADE_REF   0         0.002267   0.05       0
  30     2      ENTRE CENTROS_REF 0         0.0274147  0.04       0
```

Metadados extraídos:

| Metadado | Valor extraído |
|---|---|
| `plano_medicao` | `703.1208_TESTE` |
| `data_medicao` | `2026-08-13` |
| `hora_medicao` | `16:16:26` |
| `peca` | `27` |
| `metrologista` | `José A. Rosa Jr` |
| `mmc` | `500008` |
| `fornecedor` | `CDM` |

**28 medições**, em **2 blocos** (linhas 14–27 e 29–42), **0 pendências**.

### 6.2 Caso de uso 2 — Processar e validar a medição

**Comportamento no MVP:** `Medicao.avaliar()` compara o valor obtido com o
intervalo `[valor_nominal + tol_inferior, valor_nominal + tol_superior]`, de
forma **inclusiva** e em `Decimal`. O resultado é gravado como
`status_resultado`.

**Saída real** do `05_main.py`:

```
+----+---------------+--------+----------------+----------+----------+---------+----+-----------+
| ID | TECNICO       | EQUIP. | CARACTERISTICA | NOMINAL  | OBTIDO   | DESVIO  | UN | SITUACAO  |
+----+---------------+--------+----------------+----------+----------+---------+----+-----------+
| 1  | João da Silva | MMC001 | Diâmetro       | 50.0000  | 50.0500  | 0.0500  | mm | APROVADO  |
| 2  | João da Silva | MMC001 | Comprimento    | 100.0000 | 100.1150 | 0.1150  | mm | REPROVADO |
| 3  | João da Silva | MMC001 | Rugosidade     | 1.6000   | 1.5500   | -0.0500 | um | APROVADO  |
+----+---------------+--------+----------------+----------+----------+---------+----+-----------+
```

A medição 1 está **exatamente sobre o limite superior** (50,00 + 0,05 =
50,05) e foi aprovada — o intervalo é inclusivo. A medição 2 tem desvio de
0,115 mm sobre tolerância de 0,10 mm e foi reprovada.

### 6.3 Caso de uso 3 — Revisar e emitir certificado

**Comportamento no MVP:** a aprovação é bloqueada enquanto houver pendência
em aberto para a medição (RN13). Quando liberada, grava o número do
certificado, o usuário aprovador e as datas, e registra a ação no
histórico.

**Saída real**:

```
[5/6] Aprovacao tecnica:
  Medicao 1 -> aprovando...
  Situacao: APROVADO, certificado CERT2026001, aprovado por João da Silva
  Medicao 3 -> tentando aprovar...
  Recusada corretamente (RN13): a medição 3 possui 1 pendência(s) em aberto e não pode ser aprovada

[6/6] Pendencias em aberto:
  [ALTA] padrao: Medição sem padrão de referência vinculado — rastreabilidade metrológica não pode ser evidenciada (RN18).

Historico de acoes:
  2026-11-17 23:29:50  CERTIFICADO_EMITIDO      certificado CERT2026001
  2026-11-17 23:29:50  PENDENCIA_REGISTRADA     padrao: Medição sem padrão de referência vinculado — ...
  2026-11-17 23:29:50  MEDICAO_REGISTRADA       Rugosidade: APROVADO (1.55 um)
  2026-11-17 23:29:50  MEDICAO_REGISTRADA       Comprimento: REPROVADO (100.115 mm)
  2026-11-17 23:29:50  MEDICAO_REGISTRADA       Diâmetro: APROVADO (50.05 mm)
```

A recusa da medição 3 não é um erro do sistema: é a **regra** RN13 operando
como projetado.

### 6.4 Caso de uso 4 — Consultar histórico

**Comportamento no MVP:** a tabela `historico` registra medição registrada,
pendência registrada e certificado emitido, com autor e data/hora. A
consulta 13 de `03c_testes.sql` mostra a trilha de uma medição; a consulta
14, as ações por usuário.

### 6.5 Resumo do acervo

```
  Total de medicoes : 3
  Aprovadas         : 2
  Reprovadas        : 1
  Pendencias abertas: 1
```

---

## 7. Importação de planilhas (recurso adicional)

Esta seção descreve o webapp de upload, que executa o mesmo ETL já aplicado
na disciplina de Big Data. A inclusão se justifica por dois motivos: a AEx
pede explicitamente a importação de dados de medição (RF01–RF03) e o
Caso de Uso 01 ("Importar Arquivo de Medição"), e o protótipo de ETL da
equipe — que roda no Google Colab — **não podia ser importado** como módulo,
porque continha `!pip install` do Colab e chamava `app.launch(share=True)`
no nível superior.

A solução foi extrair a lógica para um módulo puro (`etl.py`), que serve ao
Colab e ao webapp.

### 7.1 O que o Leitor precisou resolver

Os arquivos reais da empresa foram inspecionados byte a byte antes de
qualquer linha de código de leitura. Isso revelou quatro problemas que
nenhum teste com dados inventados teria encontrado.

**Problema 1 — não existe `.xls`.** O glob `~/Downloads/*.xls` não casa com
nada. Os sete arquivos Excel da pasta são `.xlsx`/`.xlsm` (OOXML, assinatura
`50 4b 03 04` de ZIP). O `.xls` binário legado (OLE2, assinatura
`d0 cf 11 e0`) exigiria a biblioteca `xlrd`, que — ironicamente — lê
**apenas** `.xls` e não `.xlsx`.

A decisão: aceitar `.xlsx`/`.xlsm` nativamente e, para `.xls` legado,
devolver uma mensagem que orienta a conversão ("salve como .xlsx") em vez de
uma falha genérica. O `xlrd` (96 KB) pode ser adicionado como dependência
opcional se a empresa de fato enviar `.xls`.

**Problema 2 — a extensão mente.** O formato é decidido pelos **magic
bytes**, nunca pelo nome do arquivo. Um `.xlsx` renomeado para `.xls`
continua sendo OOXML e é aceito; um `.xls` legítimo recebe a orientação
correta de conversão.

**Problema 3 — dois dialetos de OOXML.** O `openpyxl` **lê** um arquivo
OOXML *strict* (namespace `purl.oclc.org/ooxml/spreadsheetml/main`) **sem
levantar exceção** e devolve `sheetnames == []` — uma lista de abas
*vazia*. Um importador que confiasse nele aceitaria o upload, não acharia
nenhuma aba e importaria **zero linhas sem avisar**. Essa é a falha mais
perigosa do conjunto, porque uma importação vazia parece uma importação
bem-sucedida.

A defesa tem duas partes: uma lista de abas vazia é tratada como **falha de
leitura** (nunca como "planilha sem dados"), e existe um leitor de reserva
implementado **apenas com a biblioteca padrão**, que identifica os
elementos do XML pelo nome local da tag (`tag.rsplit('}', 1)[-1]`) e por isso
funciona nos dois dialetos.

**Problema 4 — os rótulos não são os valores.** Na aba `Report` do formato
Calypso/MMC, os rótulos dos campos de cabeçalho estão na linha N e os
**valores na linha N+1**:

| Dado | Célula do valor | O que a versão anterior lia | Resultado errado |
|---|---|---|---|
| `Measurement Plan` | `B5` = `703.1208_TESTE` | `B4` | `'Measurement Plan'` |
| `Date` | `D5` = `2026-08-13` | `D4` | `'Date'` |
| `Order` | `F5` | `F4` | `'Order'` |
| `Drawing No.` | `B8` | `B7` | `'Drawing No.'` |
| `Part No.` | `F8` = `27` | `F7` | `'Part No.'` |
| `Metrologista` | `B11` = `José A. Rosa Jr` | `B10` | `'Metrologista'` |
| `MMC` | `D11` = `500008` | `D10` | `'MMC'` |
| `Fornecedor` | `F11` = `CDM` | `F10` | `'Fornecedor'` |

O protótipo do Colab lia **oito campos** da linha errada. A correção está
registrada em `CELULAS_METADADOS`, no ETL, e verificada por teste contra a
planilha real.

### 7.2 A tabela de medições e os dois blocos

O cabeçalho (`Characteristic`, `Actual`, `Nominal`, `Upper Tol`, `Lower
Tol`, `Deviation`) está na **linha 13**; as medições começam na 14. A aba
é localizada **pelo cabeçalho**, nunca pela posição — a aba `Report` não é
a primeira em todos os arquivos.

A planilha real tem **dois blocos** de medição: linhas 14–27 e 29–42,
separados por uma linha em branco, com o **mesmo** conjunto de
características na **mesma** peça (`Part No. = 27`). Comparando os blocos:
11 características idênticas e 3 com valor obtido diferente
(`PLANICIDADE_REF` 0,002167 × 0,002267; `62P_DIÂMETRO 2` 6,0781314 ×
6,0780314; `106P_POSIÇÃO 1` 0,1326897 × 0,1316897).

A segmentação por bloco não pode se basear em "linha vazia": a grade
construída a partir das células **não tem entrada** para as linhas vazias,
e a linha em branco é invisível como linha vazia. O fim de um bloco é
identificado pela **descontinuidade da numeração** — se a linha atual não é
a seguinte à anterior, houve uma linha em branco entre elas.

### 7.3 Idempotência: chave por origem, não por negócio

A primeira versão do plano previa a restrição
`UNIQUE (id_equipamento, ordem_servico, peca, caracteristica)`. **Ela está
errada**, e os dados reais provam isso: ela rejeitaria o segundo bloco e
perderia 14 linhas legítimas. Pior, `ordem_servico` é `NULL` nos dois
arquivos da empresa, e no SQLite valores `NULL` são **distintos** em
índices `UNIQUE` — a restrição nem sequer seria aplicada de forma
consistente.

A chave correta é por **origem**:

```sql
UNIQUE (origem_hash, origem_linha)
```

- `origem_hash` — SHA-256 do arquivo importado (16 hexadecimais);
- `origem_linha` — a linha da planilha de origem.

Reimportar o mesmo arquivo não duplica nada, e as linhas 14 e 29 coexistem
porque são linhas de origem **diferentes**. A coluna `bloco` registra a qual
bloco cada medição pertence.

### 7.4 Saneamento e validação

O ETL normaliza antes de validar:

| Situação | Tratamento | Origem |
|---|---|---|
| `???`, `----`, `N/A`, `null`, `00/00/0000` | vira `None` (ausência, não o texto) | `MarcadoresAusentes` |
| Vírgula decimal (`1.234,56`) | vira ponto (`1234.56`) | `_para_decimal` |
| Caractere de controle (`\r\n`) | vira **espaço**, não é apagado | `_limpar_texto` |
| Tolerância negativa (`-0.01`) | **preserva o sinal** (RN07) | `_para_decimal` |
| Serial do Excel (`46247`) | vira data (`2026-08-13`) | `_para_data` |

Apagar o caractere de controle em vez de substituí-lo por espaço juntaria
duas palavras: `"João\r\nSilva"` viraria `"JoãoSilva"`. O teste
`test_remove_caracteres_de_controle` fixa esse comportamento.

Campo obrigatório ausente ou não numérico não interrompe a importação: vira
**pendência** com criticidade e linha de origem, e a medição não é gravada
como válida (RN19, RN20).

### 7.5 Diagrama de sequência — importação via upload

```
Usuario      webapp.py     leitor_planilha    etl.py     servico_importacao   SQLite
   |            |                |              |              |             |
   | POST /importar (multipart) |              |              |             |
   |----------->|                |              |              |             |
   |            | checa extensao e tamanho         |              |             |
   |            | grava em /tmp com nome UUID       |              |             |
   |            |---------------->|              |              |             |
   |            |                | detecta formato por magic bytes    |             |
   |            |                | openpyxl -> fallback stdlib        |             |
   |            |                |---- grade {aba: {linha: {col: v}}}  |             |
   |            |                |              |              |             |
   |            |                | processar_grade(grade)              |             |
   |            |                |------------->|              |             |
   |            |                |              | localiza a aba pelo cabecalho|            |
   |            |                |              | le metadados das celulas de VALOR
   |            |                |              | segmenta em blocos (descontinuidade)
   |            |                |              | sanear e validar             |             |
   |            |                |              |---- ResultadoImportacao ---->|             |
   |            |                |              |              |             |
   |            |                |              |     (PREVIA: nada e gravado) |             |
   |<-----------| renderiza resultado_importacao.html                  |             |
   |            |                |              |              |             |
   | POST /confirmar              |              |              |             |
   |----------->|                |              |              |             |
   |            | le o caminho da SESSAO (nunca do formulario)        |             |
   |            | reprocessa o arquivo temporario                   |             |
   |            |---------------------------------->|             |             |
   |            |                |              | gravar(resultado)            |             |
   |            |                |              |------------->|             |
   |            |                |              |              | SAVEPOINT   |
   |            |                |              |              | INSERT tecnico/equip.
   |            |                |              |              | INSERT medicao x28
   |            |                |              |              | INSERT historico
   |            |                |              |              | RELEASE      |
   |            |                |              |              |             |
   |<-----------| redirect para /relatorio                           |             |
```

### 7.6 Arquitetura do webapp

**Flask**, e não Gradio. Gradio não está instalado, sua dependência pesa
31 MB e o `share=True` do protótipo do Colab expõe um **túnel público** —
inadequado para um sistema que recebe arquivos de uma empresa. Flask 3.1.3
tem apenas `Werkzeug` e `Jinja2` no núcleo e dá controle real sobre
multipart, status codes e rotas.

| Rota | Método | Função |
|---|---|---|
| `/` | GET | Página de upload e resumo do acervo |
| `/importar` | POST | Processa o arquivo e mostra a **prévia** (não grava) |
| `/confirmar` | POST | Grava a importação aprovada, em transação |
| `/relatorio` | GET | Relatório de calibração (JOIN de 4 tabelas) |
| `/pendencias` | GET | Lista as pendências em aberto |
| `/pendencias/<id>` | POST | Resolve uma pendência |
| `/api/medicoes` | GET | Medições em JSON |
| `/api/importar` | POST | Importação direta em JSON, com gravação |
| `/api/estatisticas` | GET | Estatísticas do acervo em JSON |

### 7.7 Prévia antes de gravar

`POST /importar` **não grava**. Ele mostra a tabela extraída, as pendências
detectadas e o que *seria* gravado. Só `POST /confirmar` persiste.

Isso atende ao fluxo alternativo do Caso de Uso 01 da AEx ("o sistema
apresenta as informações encontradas para conferência inicial… o usuário
confirma a importação") e o RF07, e evita que um arquivo errado contamine o
banco. O teste `test_previa_nao_grava_no_banco` verifica que o banco fica
vazio após a prévia.

### 7.8 Segurança do upload

| Medida | Implementação |
|---|---|
| Formato por conteúdo, não por nome | `LeitorPlanilha.detectar_formato()` lê os magic bytes |
| Limite de tamanho | `MAX_CONTENT_LENGTH` = 20 MB (resposta 413) |
| Nome do arquivo sanitizado | `werkzeug.utils.secure_filename` |
| Caminho não controlável pelo usuário | o arquivo é gravado em `/tmp` com **nome UUID**; o nome enviado é descartado |
| Travessia de diretório | eliminada: o caminho em disco nunca vem do cliente |
| Path arbitrário na confirmação | o caminho vem da **sessão** do servidor, nunca do formulário |
| Erros sem traceback | `FormatoNaoSuportadoError` → 415; `PlanilhaNaoReconhecidaError` → 422; sem arquivo → 400 |
| SQL | todo acesso usa parâmetros; nenhum caminho de arquivo entra em query |
| Escuta | apenas `127.0.0.1` (loopback) |

O webapp **não** devolve 302 em caso de falha. Um redirecionamento em uma
operação malsucedida diria "sucesso" ao cliente; a rota reexibe a página de
upload com o **status HTTP correto** (400/415/422) e a mensagem no corpo.

---

## 8. Testes automatizados

### 8.1 Cobertura

| Arquivo | Testes | Foco |
|---|---|---|
| `tests/test_regras.py` | 36 | Entidades, validação, média, desvio, desvio-padrão, veredito |
| `tests/test_persistencia.py` | 25 | Conexão, PRAGMA, integridade, transações, serviço |
| `tests/test_leitor.py` | 19 | Magic bytes, erros de formato, OOXML estrito, planilhas reais |
| `tests/test_etl.py` | 33 | Saneamento, metadados, blocos, pendências, planilha real |
| `tests/test_webapp.py` | 28 | Rotas, prévia, confirmação, idempotência, segurança |
| **Total** | **141** | |

Comando:

```bash
python -m unittest discover -s tests -v
```

### 8.2 Saída real

```
Ran 141 tests in 12.447s

OK
```

### 8.3 O que os testes encontraram

Os testes não são decorativos: eles encontraram defeitos reais durante o
desenvolvimento.

| Defeito | Como foi detectado |
|---|---|
| `em_transacao` desfazia gravações anteriores ao bloco | `test_transacao_desfaz_em_erro` |
| `origem_arquivo` gravava o nome temporário (UUID) em vez do original | `test_confirmacao_grava_a_origem` |
| Rotas HTML de erro respondiam 302 em vez de 4xx | `test_rota_html_devolve_o_status_real_de_erro` |
| Caractere de controle era apagado, juntando palavras | `test_remove_caracteres_de_controle` |
| Extensão `.xls` com conteúdo OOXML era rejeitada antes da detecção | `test_extensao_xls_com_conteudo_ooxml_e_aceito` |
| Blocos de medição não eram segmentados (grade sem linhas vazias) | `test_linha_em_branco_separa_blocos` |

### 8.4 Testes contra os arquivos reais

Os testes de ETL e de leitor usam as planilhas reais da empresa quando
presentes em `~/Downloads`, e são pulados com `skipUnless` caso não
estejam. Isso garante que as asserções sobre **28 registros**, **2 blocos**,
**linhas de origem distintas** e os valores de metadados sejam verificadas
contra o arquivo de verdade, e não contra um fixture inventado.

---

## 9. Limitações e próximos passos

Esta entrega cobre a Parte 1. O que fica para as partes seguintes:

| Item | Requisito | Situação |
|---|---|---|
| Incerteza da medição (UV) | RN12, RN24 | **Não implementada.** Os limites de incerteza dependem de regra técnica validada pela Schulz; modelar as componentes sem a regra seria inventar critério. As colunas e a arquitetura já suportam a inclusão. |
| Emissão do certificado em PDF | RF12, RF13 | **Não implementada.** Depende da incerteza. O registro do certificado no banco já existe (`certificado_numero`, `certificado_data`, `usuario_aprovacao`). |
| Controle de acesso | RNF01 | **Não implementado.** O webapp escuta apenas em `127.0.0.1`. Autenticação e autorização são escopo de uma parte própria. |
| Disponibilidade e desempenho | RNF02, RNF06 | **Não implementados.** O MVP usa SQLite local, sem SLA de disponibilidade. |
| Suporte a `.xls` legado | — | **Opcional.** Depende de `xlrd` e da confirmação de que a empresa envia esse formato. |
| Conversão de unidades | RN08 | **Declarada como fora do escopo** pelo próprio requisito: o sistema preserva a unidade, sem converter. |
| Testes de carga e concorrência | — | **Não implementados.** O SQLite serializa escrita; o volume da empresa não foi estimado. |

### 9.1 Decisões que dependem da empresa

1. **A empresa envia `.xls` binário legado ou `.xlsx`/`.xlsm`?** Nos
   arquivos disponíveis, todos são OOXML.
2. **Os dois blocos de medição da mesma peça são repetição legítima ou
   duplicata indevida?** O sistema aceita os dois e sinaliza como
   pendência de criticidade MÉDIA; se a empresa considerar duplicata, a
   criticidade sobe.
3. **O webapp será local ou acessível em rede?** A resposta muda a parte de
   segurança (autenticação, TLS).

---

## 10. Referências

1. SCHULZ S.A. *Projeto Aplicado I — Roteiro de Instruções de Entrega AV03*. SENAI, 2026.
2. SCHULZ S.A. *Projeto Aplicado I — Identificação do Problema e Levantamento de Requisitos (AEx)*. SENAI, 2026.
3. SCHULZ S.A. *Projeto Aplicado I — Entrega 02: Modelagem e Implementação de Banco de Dados*. SENAI, 2026.
4. SCHULZ S.A. *Planilha MMC — Relatório de Resultado de Medição (Calypso Measuring Result)*. Arquivo interno `.xlsm`.
5. SCHULZ S.A. *Registro MMC*. Planilha interna `.xlsx`.
6. SCHULZ S.A. *Dispositivo de controle*. Planilha interna `.xlsx` (OOXML estrito).
7. Python Software Foundation. *Python Documentation — `sqlite3` Module*. Disponível em <https://docs.python.org/3/library/sqlite3.html>. Acesso em nov. 2026.
8. Python Software Foundation. *Python Documentation — `decimal` Module*. Disponível em <https://docs.python.org/3/library/decimal.html>. Acesso em nov. 2026.
9. Python Software Foundation. *Python Documentation — `unittest` Module*. Disponível em <https://docs.python.org/3/library/unittest.html>. Acesso em nov. 2026.
10. Python Software Foundation. *Python Documentation — `importlib` Module*. Disponível em <https://docs.python.org/3/library/importlib.html>. Acesso em nov. 2026.
11. SQLite Consortium. *SQLite Documentation — Foreign Key Support*. Disponível em <https://www.sqlite.org/foreignkeys.html>. Acesso em nov. 2026.
12. SQLite Consortium. *SQLite Documentation — `PRAGMA foreign_keys`*. Disponível em <https://www.sqlite.org/pragma.html#pragma_foreign_keys>. Acesso em nov. 2026.
13. SQLite Consortium. *SQLite Documentation — `ALTER TABLE`*. Disponível em <https://www.sqlite.org/lang_altertable.html>. Acesso em nov. 2026.
14. Microsoft. *\[MS-XLSX] Office Open XML File Format*. Disponível em <https://learn.microsoft.com/openspecs/office_standards/ms-xlsx/>. Acesso em nov. 2026.
15. Ecma International. *ECMA-376 — Office Open XML File Formats*. 5ª ed. 2016.
16. Pallets. *Flask Documentation*. Disponível em <https://flask.palletsprojects.com/>. Acesso em nov. 2026.
17. Healey, M. *openpyxl — A Python library to read/write Excel 2010 xlsx/xlsm files*. Disponível em <https://openpyxl.readthedocs.io/>. Acesso em nov. 2026.
18. Fowler, M. *Patterns of Enterprise Application Architecture*. Addison-Wesley, 2002. (Repository e Service Layer.)
19. Fowler, M. *Refactoring: Improving the Design of Existing Code*. 2ª ed. Addison-Wesley, 2018. (Extração de classe, Rename Method.)
20. ISO/IEC 29500-1:2016. *Information technology — Document description and processing languages — Office Open XML file formats — Part 1*. ISO, 2016.

---

## Anexo A — Mapeamento dos critérios do roteiro AV03

| Critério do roteiro | Onde é atendido | Verificação |
|---|---|---|
| **Item 1** — Classes de domínio (`Tecnico`, `Equipamento`, `Medicao`) com atributos, validação de tolerância e CRUD sobre SQLite | `04_classes.py` — classes `Tecnico` (§3.2 do doc), `Equipamento`, `Medicao`, repositórios e `ServicoCalibracao` | `tests/test_regras.py` (36) + `tests/test_persistencia.py` (25) |
| **Item 1** — Classe de conexão e persistência que executa `INSERT`, `SELECT`, `UPDATE` e gerencia a conexão com SQLite | `ConexaoSQLite` — `executar()`, `consultar()`, `em_transacao()` | `test_pragma_de_chave_estrangeira_ligado`, `test_transacao_desfaz_em_erro` |
| **Item 1** — `Tecnico` com `id_tecnico`, `matricula`, `nome`, `setor` | `Tecnico.matricula`, alias `codigo` | `test_matricula_expoe_o_codigo` |
| **Item 1** — `Equipamento` com `id_equipamento`, `codigo_tag`, `descricao`, `fabricante` | `Equipamento.codigo_tag`, `.descricao`, alias `codigo`/`nome` | `test_alias_do_roteiro` |
| **Item 1** — `Medicao` com a lógica de validação do status pelas tolerâncias e pelo valor obtido | `Medicao.avaliar()` / `status_resultado()` | `test_exatamente_no_limite_superior_aprovado` e outros 4 |
| **Item 2** — Script principal que instancia objetos, insere registros de teste, executa JOIN e exibe o relatório no terminal | `05_main.py` — seções [1/6] a [6/6] | saída real na §6.2 |
| **Item 3** — Documento sobre os padrões de POO | §3.1 (tabela de 12 padrões) e §3.6 (código) | este documento |
| **Item 3** — Diagramação textual/UML das classes | §3.2 (diagrama de classes) e §3.4 (diagrama de sequência) | este documento |
| **Item 3** — Tratamento de erros SQL | §4.3 (tabela de tradução) e §4.4 (transações) | `test_erro_do_driver_vira_excecao_de_dominio` |
| **Item 3** — Validação do fluxo funcional do MVP | §6 (os 4 casos de uso, com saída real) | este documento |
| Linguagem aceita (Java ou Python) | Python 3.8+ | §2.1 |
| Execução no VS Code ou IDE de escolha | projeto sem dependência externa no núcleo | `README.md` |
| Versionamento em repositório GitHub | `README.md` mapeia os arquivos; o repositório é criado pelo Rafael | §9 do plano |
| Envio em ZIP com PDF explicativo e link do repositório | `06_mvp_parte1.md` convertido em PDF | §11 |
| **Critérios de avaliação** | | |
| — Qualidade da modelagem POO | 12 padrões aplicados, hierarquia de exceções, encapsulamento, validação na construção | §3 |
| — Correto tratamento de dados com o SQLite | parâmetros em 100% das queries, tradução de erros, PRAGMA por conexão, `SAVEPOINT` | §4 |
| — Alinhamento aos requisitos do projeto | RN, RF e RNF mapeados | §5, Anexo B |
| — Organização do código | `04_classes.py`/`05_main.py` com os nomes do roteiro; `schulz_mvp/` para o separável; testes separados | §2.2, `README.md` |

---

## Anexo B — Mapeamento da AEx (RF / RN / RNF)

### Requisitos funcionais

| RF | Situação | Onde |
|---|---|---|
| RF01 | **Implementado** | `leitor_planilha.py` + `etl.py` + `POST /importar` |
| RF02 | **Implementado** | `etl.py` — `CELULAS_METADADOS` |
| RF03 | **Implementado** | `etl.py` — extração das 5 colunas de resultado |
| RF04 | **Implementado** | `Equipamento` + `EquipamentoRepositorio` |
| RF05 | **Implementado** | `Tecnico`, `Equipamento` + relatório |
| RF06 | **Implementado** | FKs + `ServicoCalibracao` |
| RF07 | **Implementado** | `etl.py` gera pendências; prévia antes de gravar |
| RF08 | **Implementado** | `Medicao.media()` |
| RF09 | **Implementado** | `Medicao.desvio()` |
| RF10 | **Não implementado** | incerteza — depende de regra técnica validada (RN12/RN24) |
| RF11 | **Implementado** | `ServicoCalibracao.registrar_medicao()` |
| RF12 | **Não implementado** | emissão do certificado em PDF — depende de RF10 |
| RF13 | **Não implementado** | emissão do certificado em PDF |
| RF14 | **Implementado** | `GET /relatorio`, `GET /api/medicoes` |
| RF15 | **Implementado** | tabela `historico` |

### Regras de negócio

| RN | Situação |
|---|---|
| RN01 | Implementado |
| RN02 | Implementado |
| RN03 | Não aplicável a esta parte (registro de usuários do AVA) |
| RN04 | Implementado |
| RN05 | Não aplicável a esta parte (validação de login) |
| RN06 | Implementado |
| RN07 | Implementado |
| RN08 | Implementado (preservação; conversão declarada fora do escopo) |
| RN09 | Implementado |
| RN10 | Implementado |
| RN11 | Implementado |
| RN12 | **Não implementado** — incerteza |
| RN13 | Implementado |
| RN14 | Implementado |
| RN15 | Implementado |
| RN16 | Implementado |
| RN17 | Implementado |
| RN18 | Implementado |
| RN19 | Implementado |
| RN20 | Implementado |
| RN21 | Implementado |
| RN22 | Implementado |
| RN23 | Não aplicável a esta parte (dados do AVA) |
| RN24 | Implementado |

### Requisitos não funcionais

| RNF | Situação |
|---|---|
| RNF01 (controle de acesso) | **Não implementado** — escopo de parte própria; o webapp escuta apenas em loopback |
| RNF02 (desempenho) | **Não implementado** — sem SLA definido; SQLite local é adequado ao volume da empresa |
| RNF03 (rastreabilidade / auditoria) | **Implementado** — tabela `historico` |
| RNF04 (integridade e consistência) | Implementado — FKs, `CHECK`, `UNIQUE`, transações |
| RNF05 (disponibilidade da informação) | Parcial — persistência local em arquivo |
| RNF06 (disponibilidade do sistema) | **Não implementado** — sem SLA; escopo de parte própria |
| RNF07 (backup e recuperação) | Parcial — o banco é um arquivo, versionável e copiável; rotina de backup fora do escopo |

---

## Anexo C — Registro de versões

| Versão | Data | Autor | Mudança |
|---|---|---|---|
| 1.0 | 17/11/2026 | Equipe AV03 | Versão inicial do MVP (Parte 1): classes POO, persistência SQLite, regras metrológicas, importação de planilhas e webapp de upload |

---

*Documento gerado como parte da Entrega 03 (AV03) do Projeto Aplicado I — Schulz S.A.*
