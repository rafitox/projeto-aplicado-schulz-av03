# Projeto Aplicado I — Entrega 03 (AV03)

**Atividade Avaliativa:** AV03 — Construção do MVP (Parte 1): Implementação das classes do sistema em POO e conexão com banco relacional (SQLite)
**Empresa parceira:** Schulz S.A.
**Linguagem:** Python 3
**Banco de dados:** SQLite

---

## O que esta entrega entrega

O roteiro da AV03 pede três itens. Este repositório entrega os três, mais um
webapp de upload que reaproveita o ETL já usado na disciplina de Big Data.

| Item do roteiro | Arquivo | Situação |
|---|---|---|
| 1. Classes de domínio e conexão SQL | `04_classes.py` | entregue |
| 2. Script principal de demonstração | `05_main.py` | entregue |
| 3. Documentação técnica do MVP (Parte 1) | `06_mvp_parte1.md` | entregue |
| — Importação de planilhas via webapp | `schulz_mvp/`, `07_webapp.py` | adicionado |

---

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| `01_estrutura.md` | Modelo conceitual v3 e justificativa da organização dos dados |
| `02_dicionario.md` | Dicionário de dados v3 (extraído do schema real) |
| `03_banco.sql` | DDL do schema v3 (`CREATE TABLE`) |
| `03b_migracao.sql` | Migração do schema v2 (Entrega 02) para o v3 |
| `03c_testes.sql` | 18 consultas de teste do banco |
| `04_classes.py` | **Item 1** — entidades, conexão, repositórios e serviço |
| `05_main.py` | **Item 2** — script de demonstração com JOIN de 4 tabelas |
| `06_mvp_parte1.md` | **Item 3** — documentação técnica do MVP |
| `07_webapp.py` | Ponto de entrada do webapp de upload |
| `schulz_mvp/_loader.py` | Carrega `04_classes.py` (nome com prefixo numérico) |
| `schulz_mvp/leitor_planilha.py` | Leitor Excel (openpyxl + fallback stdlib) |
| `schulz_mvp/etl.py` | ETL puro: extração, saneamento, validação |
| `schulz_mvp/servico_importacao.py` | Gravação do ETL no SQLite |
| `schulz_mvp/relatorio.py` | Relatório de calibração no terminal |
| `schulz_mvp/webapp.py` | Aplicação Flask e rotas |
| `schulz_mvp/templates/` | Templates Jinja2 (upload, prévia, relatório, pendências) |
| `tests/` | 144 testes automatizados (`unittest`) |
| `requirements.txt` | Dependências **opcionais** do webapp |
| `tools/gerar_pdf.py` | Gera o PDF do documento técnico (pandoc + LaTeX) |
| `tools/gerar_planilha_exemplo.py` | Gera uma planilha de exemplo no formato MMC |

---

## Como executar

### Requisitos

- **Python 3.8 ou superior.**
- O **núcleo** (`04_classes.py`, `05_main.py`) usa **somente a biblioteca
  padrão**. Não é preciso instalar nada.

### 1. Script de demonstração (Item 2 do roteiro)

```bash
python 05_main.py
```

Cria o `calibracao.db` a partir de `03_banco.sql`, semeia técnico, equipamento
e padrão, registra três medições (uma aprovada no limite exato, uma
reprovada e uma com pendência), executa o JOIN de 4 tabelas e imprime o
relatório de calibração no terminal.

Opções: `python 05_main.py --banco outro.db`

### 2. Testes

```bash
python -m unittest discover -s tests -v
```

141 testes, sem dependências externas. Também rodam sob `pytest`, se o
avaliador o tiver.

### 3. Webapp de upload (recurso adicional)

```bash
pip install -r requirements.txt
python 07_webapp.py
```

Abre em <http://127.0.0.1:5000>. Envie uma planilha `.xlsx`/`.xlsm` da MMC:
o sistema mostra uma **prévia** com os dados extraídos e as pendências
detectadas, e só grava no banco depois da confirmação.

Para testar sem usar um arquivo da empresa, gere uma planilha de exemplo
com dados fictícios, no mesmo layout do formato Calypso/MMC:

```bash
python tools/gerar_planilha_exemplo.py
```

### 4. Gerar o PDF do documento técnico

```bash
python tools/gerar_pdf.py
```

Converte `06_mvp_parte1.md` em PDF (`pandoc` + `pdflatex`). O script
ajusta os caracteres que o LaTeX não aceita, sem alterar o Markdown do
projeto.

---

## Ferramentas

| Comando | O que faz |
|---|---|
| `python 05_main.py` | Demonstração do Item 2 do roteiro |
| `python -m unittest discover -s tests -v` | 144 testes |
| `python 07_webapp.py` | Webapp de upload em `127.0.0.1:5000` |
| `python tools/gerar_planilha_exemplo.py` | Planilha de teste fictícia |
| `python tools/gerar_pdf.py` | PDF do documento técnico |
| `sqlite3 calibracao.db < 03c_testes.sql` | 18 consultas de verificação |

## Arquitetura em uma linha

```
webapp.py → servico_importacao.py → etl.py → leitor_planilha.py → 04_classes.py → stdlib
```

A dependência é unidirecional e `04_classes.py` nunca importa o pacote
`schulz_mvp`. O `etl.py` não importa Flask — é o mesmo código que roda no
Colab e no webapp.

---

## Vocabulário

O roteiro da AV03 nomeia os atributos das classes de um jeito
(`matricula`, `codigo_tag`, `descricao`) e o banco usa outro (`codigo`,
`nome`), herdado da Entrega 02. As **entidades** seguem o roteiro; as
**colunas** seguem o banco; a tradução fica em `to_row()`/`from_row()`, e os
aliases antigos continuam disponíveis em Python.

| Entidade (roteiro) | Coluna (banco) | Alias em Python |
|---|---|---|
| `Tecnico.matricula` | `tecnico_solicitante.codigo` | `Tecnico.codigo` |
| `Equipamento.codigo_tag` | `equipamento.codigo` | `Equipamento.codigo` |
| `Equipamento.descricao` | `equipamento.nome` | `Equipamento.nome` |

---

## Banco de dados

O `calibracao.db` **não** é versionado — é gerado ao rodar o sistema.

Para evoluir um banco já existente da Entrega 02:

```bash
cp calibracao.db calibracao_v3.db
sqlite3 calibracao_v3.db < 03b_migracao.sql
```

---

## Observações

- O webapp escuta apenas em `127.0.0.1` (loopback). Controle de acesso
  (RNF01) está fora do escopo desta parte e é declarado como limitação.
- A incerteza (UV), a emissão do certificado em PDF e o controle de acesso
  são as partes seguintes do projeto.
