# 01 - Organização dos Dados (v3)

## Modelo Conceitual

O banco de dados proposto organiza as informações relacionadas ao processo de calibração da Schulz S.A.

Na situação analisada na Entrega 01, os dados utilizados no processo de medição e na emissão dos certificados estavam distribuídos entre arquivos de medição, planilhas de controle e cadastros auxiliares.

A **Entrega 02** organizou essas informações em três entidades principais: **Técnico/Solicitante, Equipamento e Medição**.

A **Entrega 03 (AV03)** evolui esse modelo para seis entidades, cada uma nova tabela ligada a um requisito concreto da AEx:

| Entidade | Papel no processo | Requisito que a motiva |
|---|---|---|
| Técnico/Solicitante | Quem realiza ou solicita a medição | RN02, RF05 |
| Equipamento | Instrumento de medição (MMC) | RN02, RF04 |
| Padrão de medição | Instrumento de referência usado na calibração | **RN18** |
| Medição | O ensaio propriamente dito | RN01 a RN17, RN22, RN24 |
| Pendência | Informação ausente ou inválida que impede o uso do registro | **RN13, RN19, RN20** |
| Histórico | Trilha de auditoria das ações do processo | **RF15, RNF03, RN16, RN17** |

## Por que o modelo precisou crescer

A Entrega 02 modelava **o dado**: o que foi medido, por quem e em qual equipamento. A AEx do Projeto Aplicado I pede, além disso, três coisas que o modelo anterior não tinha como representar.

**A rastreabilidade metrológica (RN18).** Uma calibração só vale se for possível provar contra qual padrão ela foi feita. A tabela `padrao` guarda o instrumento de referência, o certificado desse instrumento e as datas de calibração; `medicao.id_padrao` liga cada ensaio ao padrão utilizado. Sem essa ligação, o certificado emitido não tem lastro metrológico.

**A gestão de dados ausentes (RN13, RN19, RN20).** Nem toda medição importada está completa. A tabela `pendencia` registra *o que* falta, *de qual arquivo* veio o problema e *qual a criticidade* — em vez de simplesmente recusar a importação e perder o restante do lote. Uma medição com pendência em aberto não pode ser aprovada para emissão de certificado.

**A auditoria (RF15, RNF03, RN17).** A tabela `historico` registra cada ação relevante — medição registrada, pendência aberta, certificado emitido — com autor e data/hora. Isso responde "quem alterou o quê, quando".

## Relacionamentos

```
   Tecnico/Solicitante  1 ───<  N  Medição  >─── 1  Equipamento
                                │
                                ├── N ─── 1  Padrão          (opcional, mas
                                │                                obrigatória
                                │                                para rastrear)
                                │
                                ├── 1 ───< N  Pendência       (dados ausentes)
                                │
                                └── 1 ───< N  Histórico       (trilha de auditoria)
```

Uma medição **pertence** a exatamente um técnico e a exatamente um equipamento. Isso elimina a duplicação: os dados de um técnico não se repetem em cada medição dele, e o fabricante, o modelo e o número de série do equipamento ficam cadastrados uma única vez, ainda que o instrumento seja usado em centenas de medições ao longo do tempo.

A ligação com o **padrão** é opcional no banco porque uma medição pode ser registrada antes de o padrão ser informado — mas o sistema abre uma pendência de criticidade ALTA nesse caso, e a aprovação fica bloqueada (RN13). O vínculo com o padrão é o que distingue uma calibração rastreável de um registro de resultado.

## Integridade

As chaves primárias garantem que cada registro seja identificado de forma única dentro de sua tabela. As chaves estrangeiras garantem que uma medição só exista se o técnico e o equipamento existirem, e que uma pendência ou um registro de histórico só se refiram a uma medição real.

As constraints `CHECK` protegem o domínio dos valores: `status_resultado` só aceita `APROVADO` ou `REPROVADO`, e `data_medicao` só aceita o formato `AAAA-MM-DD`. O `PRAGMA foreign_keys = ON` é aplicado **em toda conexão**, porque o SQLite associa essa configuração à conexão e não a persiste no arquivo — sem ele, uma gravação que violasse uma chave estrangeira passaria sem aviso.

## Rastreabilidade da origem (RN22)

Cada medição importada de uma planilha guarda de onde veio: `origem_arquivo` (o nome do arquivo), `origem_linha` (a linha da planilha) e `origem_hash` (o SHA-256 do arquivo). Isso permite, a qualquer momento, responder "esta medição veio daquele arquivo, daquela linha".

O `origem_hash` também é a chave de idempotência da importação: a combinação `UNIQUE (origem_hash, origem_linha)` impede que a reimportação do mesmo arquivo duplique registros. A restrição **não** é feita sobre a chave de negócio `(equipamento, ordem de serviço, peça, característica)`, porque essa combinação se repete legitimamente: a planilha da MMC repete o mesmo conjunto de características em dois blocos distintos para a mesma peça. Uma restrição nesse ponto rejeitaria o segundo bloco e perderia 14 linhas legítimas de dados.

## Consulta e manutenção

A separação das informações em entidades diferentes permite consultas relacionais que a estrutura plana não permitiria — por exemplo, o relatório de calibração que junta medição, técnico, equipamento e padrão em um único JOIN de quatro tabelas.

O modelo atende ao objetivo da Entrega 03: organizar as informações do processo de calibração em uma estrutura relacional sobre SQLite, com integridade referencial verificada, rastreabilidade metrológica, controle de dados ausentes e trilha de auditoria.
