# 02 - Dicionário de Dados (v3)

Os campos abaixo foram extraídos **do schema real do banco** (`03_banco.sql`),
e não escritos à mão: o dicionário não pode divergir do que o sistema cria.

A versão 3 evolui a Entrega 02 com três tabelas novas (`padrao`, `pendencia`,
`historico`) e novas colunas em `medicao`, cada uma motivada por um requisito
da AEx — a justificativa está em `06_mvp_parte1.md`.

| Tabela | Campo | Tipo | Chave | Descrição |
|---|---|---|---|---|
| tecnico_solicitante | id_tecnico | Inteiro | PK | Identificador único do técnico/solicitante |
| tecnico_solicitante | nome | Texto | - | Nome do técnico ou solicitante |
| tecnico_solicitante | codigo | Texto | UNIQUE | Código de identificação do técnico (matrícula) |
| tecnico_solicitante | setor | Texto | - | Setor do técnico/solicitante |
| equipamento | id_equipamento | Inteiro | PK | Identificador único do equipamento |
| equipamento | codigo | Texto | UNIQUE | Código de identificação do equipamento (TAG) |
| equipamento | nome | Texto | - | Nome ou descrição do equipamento |
| equipamento | fabricante | Texto | - | Fabricante do equipamento |
| equipamento | modelo | Texto | - | Modelo do equipamento |
| equipamento | numero_serie | Texto | UNIQUE | Número de série do equipamento |
| padrao | id_padrao | Inteiro | PK | Identificador único do padrão de medição |
| padrao | codigo | Texto | UNIQUE | Código de identificação do padrão |
| padrao | modelo | Texto | - | Modelo do padrão de medição |
| padrao | fabricante | Texto | - | Fabricante do padrão |
| padrao | numero_serie | Texto | UNIQUE | Número de série do padrão |
| padrao | ultima_calibracao | Texto | - | Data da última calibração do padrão (AAAA-MM-DD) |
| padrao | proxima_calibracao | Texto | - | Data prevista da próxima calibração (AAAA-MM-DD) |
| padrao | certificado_padrao | Texto | - | Identificação do certificado de calibração do padrão |
| medicao | id_medicao | Inteiro | PK | Identificador único da medição |
| medicao | id_tecnico | Inteiro | FK | Técnico/solicitante relacionado à medição |
| medicao | id_equipamento | Inteiro | FK | Equipamento utilizado na medição |
| medicao | id_padrao | Inteiro | FK | Padrão de medição usado como referência (rastreabilidade) |
| medicao | ordem_servico | Texto | - | Identificação da ordem de serviço |
| medicao | plano_medicao | Texto | - | Plano utilizado para realizar a medição |
| medicao | data_medicao | Texto | - | Data da medição no formato AAAA-MM-DD |
| medicao | hora_medicao | Texto | - | Horário da medição no formato HH:MM:SS |
| medicao | desenho | Texto | - | Identificação do desenho |
| medicao | peca | Texto | - | Identificação da peça avaliada |
| medicao | caracteristica | Texto | - | Parâmetro ou característica avaliada |
| medicao | valor_nominal | Real | - | Valor de referência da medição |
| medicao | tol_superior | Real | - | Limite superior de tolerância (desvio máximo aceito) |
| medicao | tol_inferior | Real | - | Limite inferior de tolerância (negativo por convenção) |
| medicao | medida_1 | Real | - | Primeiro valor obtido na medição |
| medicao | medida_2 | Real | - | Segundo valor obtido na medição |
| medicao | media | Real | - | Média das medidas válidas |
| medicao | desvio_padrao | Real | - | Desvio-padrão amostral das medidas (n-1) |
| medicao | valor_obtido | Real | - | Valor final considerado para avaliação |
| medicao | desvio | Real | - | Diferença entre o valor obtido e o valor nominal |
| medicao | unidade | Texto | - | Unidade de medida utilizada |
| medicao | status_resultado | Texto | - | Situação do resultado: APROVADO ou REPROVADO |
| medicao | certificado_numero | Texto | UNIQUE | Identificação do certificado emitido |
| medicao | usuario_aprovacao | Texto | - | Usuário responsável pela aprovação |
| medicao | data_aprovacao | Texto | - | Data da aprovação |
| medicao | certificado_data | Texto | - | Data de emissão do documento certificado |
| medicao | origem_arquivo | Texto | - | Nome do arquivo de onde a medição foi importada |
| medicao | origem_linha | Inteiro | UNIQUE | Linha do arquivo de origem da medição |
| medicao | origem_hash | Texto | UNIQUE | SHA-256 do arquivo de origem (idempotência da importação) |
| medicao | bloco | Inteiro | - | Índice do bloco de medição dentro do arquivo de origem |
| pendencia | id_pendencia | Inteiro | PK | Identificador único da pendência |
| pendencia | id_medicao | Inteiro | FK | Medição relacionada à pendência |
| pendencia | id_tecnico | Inteiro | FK | Técnico relacionado à pendência |
| pendencia | origem_arquivo | Texto | - | Arquivo onde o problema foi identificado |
| pendencia | campo | Texto | - | Campo com problema |
| pendencia | descricao | Texto | - | Descrição do problema identificado |
| pendencia | criticidade | Texto | - | Criticidade: BAIXA, MEDIA ou ALTA |
| pendencia | status | Texto | - | Situação: ABERTA, RESOLVIDA ou DESCARTADA |
| pendencia | data_registro | Texto | - | Data e hora do registro da pendência |
| pendencia | data_resolucao | Texto | - | Data e hora da resolução da pendência |
| historico | id_historico | Inteiro | PK | Identificador único do registro de histórico |
| historico | id_medicao | Inteiro | FK | Medição relacionada à ação registrada |
| historico | acao | Texto | - | Ação executada |
| historico | usuario | Texto | - | Usuário responsável pela ação |
| historico | data_hora | Texto | - | Data e hora da ação |
| historico | detalhe | Texto | - | Detalhamento da ação executada |
## Tipos de dados

No banco de dados, os identificadores numéricos são representados como **INTEGER**, os valores de medição e cálculos como **REAL**, e os códigos, nomes, datas e demais informações descritivas como **TEXT**.

Os códigos e números de série são tratados como texto porque são identificadores e podem possuir zeros à esquerda ou caracteres alfanuméricos.

As datas são armazenadas como texto no formato padronizado **AAAA-MM-DD**, e os horários em **HH:MM:SS**, o que facilita a organização e a consulta no SQLite.

## Integridade referencial

| Tabela | Campo | Referencia |
|---|---|---|
| medicao | id_tecnico | tecnico_solicitante(id_tecnico) |
| medicao | id_equipamento | equipamento(id_equipamento) |
| medicao | id_padrao | padrao(id_padrao) |
| pendencia | id_medicao | medicao(id_medicao) |
| pendencia | id_tecnico | tecnico_solicitante(id_tecnico) |
| historico | id_medicao | medicao(id_medicao) |

A chave estrangeira `medicao.id_padrao` é **opcional**: uma medição pode existir sem padrão vinculado, mas nesse caso o sistema abre uma pendência de criticidade ALTA, porque sem padrão não há rastreabilidade metrológica (RN18).

## Unicidade e idempotência

A chave `UNIQUE (origem_hash, origem_linha)` existe para tornar a **importação idempotente**: reimportar o mesmo arquivo não duplica medições.

Ela **não** é uma chave de negócio. Um mesmo conjunto de características pode legitimamente se repetir no mesmo arquivo — a planilha da MMC repete as características em dois blocos (linhas 14–27 e 29–42) para a mesma peça. Uma restrição de unicidade sobre `(equipamento, ordem de serviço, peça, característica)` rejeitaria o segundo bloco e perderia 14 linhas legítimas.

Registros criados manualmente pela aplicação não têm origem: no SQLite, valores NULL são considerados distintos em índices UNIQUE, e por isso esses registros não são bloqueados pela constraint — que é o comportamento desejado, já que uma medição digitada à mão não tem linha de origem.
