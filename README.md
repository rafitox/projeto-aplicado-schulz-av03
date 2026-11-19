# Projeto Aplicado I — Entrega 03 (AV03)

**Atividade Avaliativa:** AV03 — Construção do MVP (Parte 1): Implementação das classes do sistema em POO e conexão com banco relacional (SQLite)
**Empresa parceira:** Schulz S.A.
**Linguagem:** Python 3
**Banco de dados:** SQLite

---

## Escopo desta entrega

O roteiro da AV03 pede três itens. Este repositório entrega os três, mais um
webapp de upload que reaproveita o ETL já usado na disciplina de Big Data.

| Item do roteiro | Arquivo | Situação |
|---|---|---|
| 1. Classes de domínio e conexão SQL | `04_classes.py` | entregue |
| 2. Script principal de demonstração | `05_main.py` | entregue |
| 3. Documentação técnica do MVP (Parte 1) | `06_mvp_parte1.md` | entregue |
| — Importação de planilhas via webapp | `schulz_mvp/`, `07_webapp.py` | adicionado |
| — Publicação em túnel (Cloudflare) | `DEPLOY.md` | adicionado |

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
| `schulz_mvp/webapp.py` | Aplicação Flask, rotas e controle de acesso |
| `schulz_mvp/templates/` | Templates Jinja2 (upload, prévia, relatório, pendências, acesso) |
| `tests/` | 153 testes automatizados (`unittest`) |
| `requirements.txt` | Dependências **opcionais** do webapp |
| `tools/gerar_pdf.py` | Gera o PDF do documento técnico (pandoc + LaTeX) |
| `tools/gerar_planilha_exemplo.py` | Gera uma planilha de exemplo no formato MMC |
| `DEPLOY.md` | Publicação via Cloudflare Tunnel (túnel de teste e nomeado) |

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

153 testes, sem dependências externas. Também rodam sob `pytest`, se o
avaliador o tiver.

Sem Flask instalado, os 38 testes que dependem dele (os do webapp e o que
lê a planilha com `openpyxl`) são pulados com uma mensagem apontando o
`requirements.txt` — o núcleo continua sendo validado.

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

### 4. Publicar em um túnel (opcional)

```bash
pip install -r requirements.txt
export SCHULZ_ACCESS_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(18))')"
.venv/bin/python 07_webapp.py --port 5000          # terminal 1

~/.local/bin/cloudflared tunnel --url http://127.0.0.1:5000   # terminal 2
```

O `cloudflared` imprime uma URL pública. A aplicação continua ouvindo
apenas em `127.0.0.1`; quem aceita conexões da internet é o túnel. Os
detalhes, incluindo o túnel nomeado e o checklist de segurança, estão em
`DEPLOY.md`.

### 5. Gerar o PDF do documento técnico

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
| `python -m unittest discover -s tests -v` | 153 testes |
| `python 07_webapp.py` | Webapp de upload em `127.0.0.1:5000` |
| `python tools/gerar_planilha_exemplo.py` | Planilha de teste fictícia |
| `python tools/gerar_pdf.py` | PDF do documento técnico |
| `cloudflared tunnel --url http://127.0.0.1:5000` | Publica a aplicação em uma URL pública |
| `sqlite3 calibracao.db < 03c_testes.sql` | 18 consultas de verificação |

---

## Configuração por variável de ambiente

| Variável | Padrão | Função |
|---|---|---|
| `SCHULZ_ACCESS_TOKEN` | *(vazio)* | Token exigido em todas as rotas. Definir para expor a aplicação. |
| `SCHULZ_SECRET_KEY` | aleatória, por execução | Chave que assina o cookie de sessão. Fixar se a sessão precisar sobreviver a reinícios. |

Sem `SCHULZ_ACCESS_TOKEN`, o acesso é livre — é o comportamento do uso
local. Definido, todas as rotas exigem o token, e a aplicação pode ser
publicada com segurança.

---

## Controle de acesso (RNF01)

O requisito RNF01 está **parcialmente** implementado nesta entrega: existe
um controle de acesso por token compartilhado, o que permite publicar a
aplicação, mas **não** há autenticação com usuário e senha nem controle
por perfil de acesso. A tabela de permissões por papel é a parte
pendente.

O token é aceito de três formas:

| Forma | Uso |
|---|---|
| Formulário `/acesso` | navegador — o cookie é gravado por 8 horas |
| `?token=...` | link direto — o servidor redireciona e grava o cookie |
| `X-Access-Token: ...` | API e scripts (`curl`, automação) |

A chave secreta da sessão é gerada aleatoriamente a cada execução
(`secrets.token_hex(32)`), nunca fica escrita no código — o repositório é
público, e uma chave fixa permitiria forjar um cookie de sessão.

---

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

- O webapp escuta apenas em `127.0.0.1` (loopback) por padrão. Quem aceita
  conexões da internet, quando há publicação, é o túnel.
- A incerteza (UV), a emissão do certificado em PDF e a autenticação com
  usuário e senha (RNF01) são as partes seguintes do projeto.
- Nenhum arquivo da empresa (planilha, banco) é versionado — o `.gitignore`
  protege a lista de extensões, e o repositório contém apenas código e
  documentação.
