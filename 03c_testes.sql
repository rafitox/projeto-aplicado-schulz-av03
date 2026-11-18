-- ============================================================
-- PROJETO APLICADO I - SCHULZ S.A.
-- Entrega 03 (AV03) - MVP Parte 1
-- Consultas de teste da v3
-- Banco: SQLite
-- ============================================================
-- Como executar:
--   sqlite3 calibracao.db < 03c_testes.sql
--
-- Cada consulta é independente e devolve um conjunto de linhas. As
-- consultas 1 a 7 verificam os relacionamentos e as regras que já
-- existiam na Entrega 02; as consultas 8 a 15 exercitam o que a v3
-- acrescenta.
-- ============================================================

PRAGMA foreign_keys = ON;

-- ------------------------------------------------------------
-- 1. Todas as medições com técnico e equipamento (relacionamento)
-- ------------------------------------------------------------

SELECT
    m.id_medicao,
    t.nome AS tecnico,
    e.codigo AS equipamento,
    m.caracteristica,
    m.valor_nominal,
    m.valor_obtido,
    m.unidade,
    m.status_resultado
FROM medicao AS m
INNER JOIN tecnico_solicitante AS t ON m.id_tecnico = t.id_tecnico
INNER JOIN equipamento AS e ON m.id_equipamento = e.id_equipamento
ORDER BY m.id_medicao;

-- ------------------------------------------------------------
-- 2. Quantidade de medições por técnico (inclui quem não mediu)
-- ------------------------------------------------------------

SELECT
    t.nome AS tecnico,
    t.codigo AS matricula,
    COUNT(m.id_medicao) AS quantidade_medicoes,
    SUM(CASE WHEN m.status_resultado = 'APROVADO' THEN 1 ELSE 0 END) AS aprovadas,
    SUM(CASE WHEN m.status_resultado = 'REPROVADO' THEN 1 ELSE 0 END) AS reprovadas
FROM tecnico_solicitante AS t
LEFT JOIN medicao AS m ON t.id_tecnico = m.id_tecnico
GROUP BY t.id_tecnico, t.nome, t.codigo
ORDER BY t.nome;

-- ------------------------------------------------------------
-- 3. Medições reprovadas, com desvio calculado
-- ------------------------------------------------------------

SELECT
    m.id_medicao,
    t.nome AS tecnico,
    e.codigo AS equipamento,
    m.caracteristica,
    m.valor_nominal,
    m.valor_obtido,
    ROUND(m.valor_obtido - m.valor_nominal, 6) AS desvio,
    m.tol_inferior,
    m.tol_superior,
    m.unidade,
    m.data_medicao
FROM medicao AS m
INNER JOIN tecnico_solicitante AS t ON m.id_tecnico = t.id_tecnico
INNER JOIN equipamento AS e ON m.id_equipamento = e.id_equipamento
WHERE m.status_resultado = 'REPROVADO'
ORDER BY ABS(m.valor_obtido - m.valor_nominal) DESC;

-- ------------------------------------------------------------
-- 4. Peças com mais de uma medição da mesma característica
--    (repetição legítima: os dois blocos da planilha MMC)
-- ------------------------------------------------------------

SELECT
    m.peca,
    m.caracteristica,
    COUNT(*) AS repeticoes,
    COUNT(DISTINCT m.bloco) AS blocos,
    MIN(m.valor_obtido) AS menor_valor,
    MAX(m.valor_obtido) AS maior_valor
FROM medicao AS m
WHERE m.peca IS NOT NULL
GROUP BY m.peca, m.caracteristica
HAVING COUNT(*) > 1
ORDER BY m.peca, m.caracteristica;

-- ------------------------------------------------------------
-- 5. Medições de um período, com a média das medidas
-- ------------------------------------------------------------

SELECT
    m.data_medicao,
    t.nome AS tecnico,
    e.codigo AS equipamento,
    m.caracteristica,
    m.valor_obtido,
    m.media,
    m.desvio_padrao,
    m.status_resultado
FROM medicao AS m
INNER JOIN tecnico_solicitante AS t ON m.id_tecnico = t.id_tecnico
INNER JOIN equipamento AS e ON m.id_equipamento = e.id_equipamento
WHERE m.data_medicao BETWEEN '2026-01-01' AND '2026-12-31'
ORDER BY m.data_medicao, m.id_medicao;

-- ------------------------------------------------------------
-- 6. Verificação da integridade referencial
--    Deve devolver zero linhas.
-- ------------------------------------------------------------

SELECT
    m.id_medicao,
    m.id_tecnico,
    m.id_equipamento
FROM medicao AS m
LEFT JOIN tecnico_solicitante AS t ON m.id_tecnico = t.id_tecnico
LEFT JOIN equipamento AS e ON m.id_equipamento = e.id_equipamento
WHERE t.id_tecnico IS NULL OR e.id_equipamento IS NULL;

-- ------------------------------------------------------------
-- 7. Verificação de valores dentro das tolerâncias
--    Deve devolver zero linhas: toda medição aprovada está no
--    intervalo e toda reprovada está fora.
-- ------------------------------------------------------------

SELECT
    m.id_medicao,
    m.valor_nominal,
    m.tol_inferior,
    m.tol_superior,
    m.valor_obtido,
    m.status_resultado
FROM medicao AS m
WHERE (
    m.status_resultado = 'APROVADO'
    AND NOT (m.valor_nominal + m.tol_inferior <= m.valor_obtido
             AND m.valor_obtido <= m.valor_nominal + m.tol_superior)
) OR (
    m.status_resultado = 'REPROVADO'
    AND (m.valor_nominal + m.tol_inferior <= m.valor_obtido
         AND m.valor_obtido <= m.valor_nominal + m.tol_superior)
);

-- ============================================================
-- CONSULTAS DA v3
-- ============================================================

-- ------------------------------------------------------------
-- 8. Rastreabilidade metrológica (RN18)
--    Medições com o padrão de referência vinculado
-- ------------------------------------------------------------

SELECT
    m.id_medicao,
    m.caracteristica,
    p.codigo AS padrao,
    p.modelo AS padrao_modelo,
    p.fabricante AS padrao_fabricante,
    p.certificado_padrao,
    p.ultima_calibracao,
    p.proxima_calibracao,
    m.valor_obtido,
    m.unidade
FROM medicao AS m
INNER JOIN padrao AS p ON m.id_padrao = p.id_padrao
ORDER BY m.id_medicao;

-- ------------------------------------------------------------
-- 9. Padrões com calibração vencida
-- ------------------------------------------------------------

SELECT
    p.codigo,
    p.modelo,
    p.numero_serie,
    p.certificado_padrao,
    p.ultima_calibracao,
    p.proxima_calibracao,
    CAST(julianday('now') - julianday(p.proxima_calibracao) AS INTEGER) AS dias_vencidos
FROM padrao AS p
WHERE p.proxima_calibracao IS NOT NULL
  AND p.proxima_calibracao < date('now')
ORDER BY p.proxima_calibracao;

-- ------------------------------------------------------------
-- 10. Medições SEM padrão vinculado
--     São candidatas a pendência de rastreabilidade (RN18).
-- ------------------------------------------------------------

SELECT
    m.id_medicao,
    t.nome AS tecnico,
    e.codigo AS equipamento,
    m.caracteristica,
    m.data_medicao
FROM medicao AS m
INNER JOIN tecnico_solicitante AS t ON m.id_tecnico = t.id_tecnico
INNER JOIN equipamento AS e ON m.id_equipamento = e.id_equipamento
LEFT JOIN padrao AS p ON m.id_padrao = p.id_padrao
WHERE p.id_padrao IS NULL
ORDER BY m.id_medicao;

-- ------------------------------------------------------------
-- 11. Pendências em aberto, da mais crítica para a menos crítica
-- ------------------------------------------------------------

SELECT
    pe.id_pendencia,
    pe.criticidade,
    pe.campo,
    pe.descricao,
    pe.origem_arquivo,
    pe.data_registro,
    m.id_medicao,
    m.caracteristica
FROM pendencia AS pe
LEFT JOIN medicao AS m ON pe.id_medicao = m.id_medicao
WHERE pe.status = 'ABERTA'
ORDER BY
    CASE pe.criticidade
        WHEN 'ALTA' THEN 1
        WHEN 'MEDIA' THEN 2
        ELSE 3
    END,
    pe.data_registro DESC;

-- ------------------------------------------------------------
-- 12. Pendências agrupadas pelo campo de origem
--     Mostra de onde vem a maior parte dos problemas da importação.
-- ------------------------------------------------------------

SELECT
    pe.campo,
    COUNT(*) AS quantidade,
    MIN(pe.criticidade) AS criticidade,
    MAX(pe.descricao) AS exemplo
FROM pendencia AS pe
WHERE pe.status = 'ABERTA'
GROUP BY pe.campo
ORDER BY quantidade DESC, pe.campo;

-- ------------------------------------------------------------
-- 13. Trilha de auditoria de uma medição (RN17)
-- ------------------------------------------------------------

SELECT
    h.id_historico,
    h.data_hora,
    h.acao,
    h.usuario,
    h.detalhe
FROM historico AS h
WHERE h.id_medicao = 1
ORDER BY h.id_historico DESC;

-- ------------------------------------------------------------
-- 14. Ações por usuário
-- ------------------------------------------------------------

SELECT
    h.usuario,
    COUNT(*) AS total_acoes,
    MIN(h.data_hora) AS primeira_acao,
    MAX(h.data_hora) AS ultima_acao
FROM historico AS h
WHERE h.usuario IS NOT NULL
GROUP BY h.usuario
ORDER BY total_acoes DESC;

-- ------------------------------------------------------------
-- 15. Rastreabilidade da origem (RN22)
--     Todas as medições vindas de um arquivo específico.
--     Troque o hash pelo valor de 'origem_hash'.
-- ------------------------------------------------------------

SELECT
    m.id_medicao,
    m.origem_arquivo,
    m.origem_linha,
    m.bloco,
    m.caracteristica,
    m.valor_obtido,
    m.status_resultado
FROM medicao AS m
WHERE m.origem_hash IS NOT NULL
ORDER BY m.origem_hash, m.origem_linha;

-- ------------------------------------------------------------
-- 16. Conflito entre blocos da mesma peça e característica
--     Mede a mesma característica em blocos diferentes do mesmo
--     arquivo. Não é erro: é uma repetição a ser analisada.
-- ------------------------------------------------------------

SELECT
    m.peca,
    m.caracteristica,
    m.origem_hash,
    COUNT(DISTINCT m.bloco) AS blocos,
    GROUP_CONCAT(DISTINCT m.bloco) AS numeros_bloco,
    COUNT(DISTINCT m.valor_obtido) AS valores_distintos
FROM medicao AS m
WHERE m.peca IS NOT NULL AND m.origem_hash IS NOT NULL
GROUP BY m.peca, m.caracteristica, m.origem_hash
HAVING COUNT(DISTINCT m.bloco) > 1
ORDER BY m.peca, m.caracteristica;

-- ------------------------------------------------------------
-- 17. Resumo do acervo
-- ------------------------------------------------------------

SELECT
    COUNT(*) AS total_medicoes,
    SUM(CASE WHEN status_resultado = 'APROVADO' THEN 1 ELSE 0 END) AS aprovadas,
    SUM(CASE WHEN status_resultado = 'REPROVADO' THEN 1 ELSE 0 END) AS reprovadas,
    COUNT(DISTINCT id_tecnico) AS tecnicos,
    COUNT(DISTINCT id_equipamento) AS equipamentos,
    COUNT(DISTINCT id_padrao) AS padroes,
    COUNT(DISTINCT origem_hash) AS arquivos_importados
FROM medicao;

-- ------------------------------------------------------------
-- 18. Verificação de integridade do próprio banco
--     PRAGMA foreign_key_check deve devolver zero linhas.
-- ------------------------------------------------------------

PRAGMA foreign_key_check;
