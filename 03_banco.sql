-- ============================================================
-- PROJETO APLICADO I - SCHULZ S.A.
-- Entrega 03 (AV03) - MVP Parte 1
-- Schema v3: modelo relacional estendido
-- Banco: SQLite
-- ============================================================
-- Diferencas em relacao a Entrega 02 (v2):
--   * tabela padrao  (RN18 - rastreabilidade metrologica)
--   * tabela pendencia (RN13/RN19/RN20 - pendencias de correcao)
--   * tabela historico (RF15/RNF03/RN16/RN17 - trilha de auditoria)
--   * colunas novas em medicao: id_padrao, desvio_padrao,
--     origem_arquivo, origem_linha, origem_hash, bloco, certificado_data
-- ============================================================

PRAGMA foreign_keys = ON;

-- ============================================================
-- REMOÇÃO DAS TABELAS EXISTENTES
-- ============================================================

DROP TABLE IF EXISTS historico;
DROP TABLE IF EXISTS pendencia;
DROP TABLE IF EXISTS medicao;
DROP TABLE IF EXISTS padrao;
DROP TABLE IF EXISTS equipamento;
DROP TABLE IF EXISTS tecnico_solicitante;

-- ============================================================
-- 1. TÉCNICO / SOLICITANTE
-- ============================================================

CREATE TABLE tecnico_solicitante (
    id_tecnico INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    codigo TEXT NOT NULL UNIQUE,
    setor TEXT
);

-- ============================================================
-- 2. EQUIPAMENTO
-- ============================================================

CREATE TABLE equipamento (
    id_equipamento INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,
    nome TEXT NOT NULL,
    fabricante TEXT,
    modelo TEXT,
    numero_serie TEXT UNIQUE
);

-- ============================================================
-- 3. PADRÃO DE MEDIÇÃO
-- Instrumento de referência utilizado na calibração. Vinculado à
-- medição para garantir a rastreabilidade metrológica (RN18).
-- ============================================================

CREATE TABLE padrao (
    id_padrao INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,
    modelo TEXT NOT NULL,
    fabricante TEXT,
    numero_serie TEXT UNIQUE,
    ultima_calibracao TEXT,
    proxima_calibracao TEXT,
    certificado_padrao TEXT
);

-- ============================================================
-- 4. MEDIÇÃO
-- ============================================================

CREATE TABLE medicao (
    id_medicao INTEGER PRIMARY KEY AUTOINCREMENT,

    id_tecnico INTEGER NOT NULL,
    id_equipamento INTEGER NOT NULL,
    id_padrao INTEGER REFERENCES padrao(id_padrao),

    ordem_servico TEXT,
    plano_medicao TEXT,

    data_medicao TEXT NOT NULL
        CHECK (data_medicao GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    hora_medicao TEXT
        CHECK (hora_medicao IS NULL
               OR hora_medicao GLOB '[0-9][0-9]:[0-9][0-9]:[0-9][0-9]'),

    desenho TEXT,
    peca TEXT,
    caracteristica TEXT NOT NULL,

    valor_nominal REAL NOT NULL,
    tol_superior REAL NOT NULL,
    tol_inferior REAL NOT NULL,

    medida_1 REAL,
    medida_2 REAL,
    media REAL,
    desvio_padrao REAL,
    valor_obtido REAL NOT NULL,
    desvio REAL,

    unidade TEXT NOT NULL,
    status_resultado TEXT NOT NULL
        CHECK (status_resultado IN ('APROVADO', 'REPROVADO')),

    certificado_numero TEXT UNIQUE,
    usuario_aprovacao TEXT,
    data_aprovacao TEXT,
    certificado_data TEXT,

    -- Rastreabilidade da origem (RN22) e idempotência de importação (RN21).
    -- origem_hash é o SHA-256 do arquivo importado; origem_linha é a linha
    -- de origem na planilha. O par torna a importação idempotente.
    origem_arquivo TEXT,
    origem_linha INTEGER,
    origem_hash TEXT,
    -- Índice do bloco de medição dentro do arquivo. A planilha MMC pode
    -- repetir o mesmo conjunto de características em blocos distintos.
    bloco INTEGER NOT NULL DEFAULT 1 CHECK (bloco >= 1),

    FOREIGN KEY (id_tecnico)
        REFERENCES tecnico_solicitante(id_tecnico),

    FOREIGN KEY (id_equipamento)
        REFERENCES equipamento(id_equipamento),

    FOREIGN KEY (id_padrao)
        REFERENCES padrao(id_padrao),

    UNIQUE (origem_hash, origem_linha)
);

-- ============================================================
-- 5. PENDÊNCIA
-- Registro de informação ausente ou inválida que impede o uso do
-- registro para emissão de certificado (RN13/RN19/RN20).
-- ============================================================

CREATE TABLE pendencia (
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

-- ============================================================
-- 6. HISTÓRICO
-- Trilha de auditoria das ações realizadas no processo (RF15/RNF03/RN17).
-- ============================================================

CREATE TABLE historico (
    id_historico INTEGER PRIMARY KEY AUTOINCREMENT,
    id_medicao INTEGER REFERENCES medicao(id_medicao),
    acao TEXT NOT NULL,
    usuario TEXT,
    data_hora TEXT NOT NULL,
    detalhe TEXT
);

-- ============================================================
-- ÍNDICES DE APOIO
-- ============================================================

CREATE INDEX idx_medicao_data ON medicao(data_medicao);
CREATE INDEX idx_medicao_equipamento ON medicao(id_equipamento);
CREATE INDEX idx_medicao_tecnico ON medicao(id_tecnico);
CREATE INDEX idx_pendencia_status ON pendencia(status);
CREATE INDEX idx_historico_medicao ON historico(id_medicao);
