-- ============================================================
-- PROJETO APLICADO I - SCHULZ S.A.
-- Entrega 03 (AV03) - MVP Parte 1
-- Migração do schema v2 (Entrega 02) para o schema v3
-- Banco: SQLite
-- ============================================================
-- Uso:
--   cp calibracao.db calibracao_v3.db
--   sqlite3 calibracao_v3.db < 03b_migracao.sql
--
-- Este script é ADITIVO: não apaga nem recria as tabelas da v2.
-- Para recriar o banco do zero, use 03_banco.sql.
-- ============================================================

PRAGMA foreign_keys = OFF;

-- ============================================================
-- 1. NOVAS TABELAS
-- ============================================================

CREATE TABLE IF NOT EXISTS padrao (
    id_padrao INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,
    modelo TEXT NOT NULL,
    fabricante TEXT,
    numero_serie TEXT UNIQUE,
    ultima_calibracao TEXT,
    proxima_calibracao TEXT,
    certificado_padrao TEXT
);

CREATE TABLE IF NOT EXISTS pendencia (
    id_pendencia INTEGER PRIMARY KEY AUTOINCREMENT,
    id_medicao INTEGER REFERENCES medicao(id_medicao),
    id_tecnico INTEGER REFERENCES tecnico_solicitante(id_tecnico),
    origem_arquivo TEXT,
    campo TEXT NOT NULL,
    descricao TEXT NOT NULL,
    criticidade TEXT NOT NULL
        CHECK (criticidade IN ('BAIXA', 'MEDIA', 'ALTA')),
    status TEXT NOT NULL
        CHECK (status IN ('ABERTA', 'RESOLVIDA', 'DESCARTADA')),
    data_registro TEXT NOT NULL,
    data_resolucao TEXT
);

CREATE TABLE IF NOT EXISTS historico (
    id_historico INTEGER PRIMARY KEY AUTOINCREMENT,
    id_medicao INTEGER REFERENCES medicao(id_medicao),
    acao TEXT NOT NULL,
    usuario TEXT,
    data_hora TEXT NOT NULL,
    detalhe TEXT
);

-- ============================================================
-- 2. NOVAS COLUNAS EM medicao
-- ============================================================
-- O SQLite não aceita ADD COLUMN com constraint UNIQUE, por isso a
-- unicidade de (origem_hash, origem_linha) é criada como índice na
-- seção 3, e não como constraint de coluna.
-- ============================================================

ALTER TABLE medicao ADD COLUMN id_padrao INTEGER REFERENCES padrao(id_padrao);
ALTER TABLE medicao ADD COLUMN desvio_padrao REAL;
ALTER TABLE medicao ADD COLUMN origem_arquivo TEXT;
ALTER TABLE medicao ADD COLUMN origem_linha INTEGER;
ALTER TABLE medicao ADD COLUMN origem_hash TEXT;
ALTER TABLE medicao ADD COLUMN bloco INTEGER NOT NULL DEFAULT 1;
ALTER TABLE medicao ADD COLUMN certificado_data TEXT;

-- ============================================================
-- 3. ÍNDICE ÚNICO DE IDEMPOTÊNCIA DE IMPORTAÇÃO (RN21)
-- ============================================================
-- Impede que a reimportação do mesmo arquivo duplique medições.
-- Registros criados manualmente (sem origem) ficam com NULL e não
-- são bloqueados — no SQLite, NULLs são distintos em índices UNIQUE.
-- ============================================================

CREATE UNIQUE INDEX IF NOT EXISTS idx_medicao_origem
    ON medicao(origem_hash, origem_linha);

-- ============================================================
-- 4. ÍNDICES DE APOIO
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_medicao_data ON medicao(data_medicao);
CREATE INDEX IF NOT EXISTS idx_medicao_equipamento ON medicao(id_equipamento);
CREATE INDEX IF NOT EXISTS idx_medicao_tecnico ON medicao(id_tecnico);
CREATE INDEX IF NOT EXISTS idx_pendencia_status ON pendencia(status);
CREATE INDEX IF NOT EXISTS idx_historico_medicao ON historico(id_medicao);

-- ============================================================
-- 5. LIMPEZA DE DUPLICATAS PRÉ-EXISTENTES
-- ============================================================
-- A v2 não possuía a chave de origem, então não há duplicatas por
-- (origem_hash, origem_linha). Este bloco é defensivo: remove
-- duplicatas exatas de (id_tecnico, id_equipamento, caracteristica,
-- data_medicao, valor_obtido) que impediriam a criação do índice.
-- ============================================================

DELETE FROM medicao
WHERE id_medicao NOT IN (
    SELECT MIN(id_medicao)
    FROM medicao
    GROUP BY id_tecnico, id_equipamento, caracteristica,
             data_medicao, valor_obtido
);

PRAGMA foreign_keys = ON;
