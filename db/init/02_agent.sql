-- ============================================================
-- BizIntel AI - Schema AI Agent Phase 4 (memory + observability)
--
--   agent_messages : conversation memory per session_id (KONTEKS saja)
--   agent_runs     : audit/observability untuk setiap eksekusi /api/chat
--
-- Pemisahan tanggung jawab (jangan tertukar):
--   PostgreSQL (sales/daily_metrics) = source of truth analytics
--   ChromaDB                         = source of truth business knowledge
--   joblib artifacts                 = source of truth model ML
--   agent_messages                   = HANYA konteks percakapan
--   agent_runs                       = HANYA audit/observability
--
-- Idempotent (IF NOT EXISTS) agar aman dijalankan ulang; dieksekusi
-- otomatis oleh docker-entrypoint-initdb.d saat container baru dibuat,
-- dan secara lazy oleh backend/app/agent/ensure.py (satu sumber DDL).
-- Tidak ada kolom credential/secret. Semua akses memakai parameterized
-- query; session_id tidak pernah menjadi SQL identifier.
-- ============================================================

CREATE TABLE IF NOT EXISTS agent_messages (
    message_id   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id   VARCHAR(128) NOT NULL,
    role         VARCHAR(8)  NOT NULL CHECK (role IN ('human', 'ai')),
    content      TEXT        NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_messages_session
    ON agent_messages (session_id, message_id);

CREATE TABLE IF NOT EXISTS agent_runs (
    run_id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id         VARCHAR(128) NOT NULL,
    user_message       TEXT        NOT NULL,
    assistant_message  TEXT,
    tools_used         JSONB       NOT NULL DEFAULT '[]',
    status             VARCHAR(32) NOT NULL CHECK (status IN ('SUCCESS', 'ERROR')),
    error_type         VARCHAR(128),
    latency_ms         INTEGER,
    model_name         VARCHAR(128),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_runs_session ON agent_runs (session_id);

CREATE INDEX IF NOT EXISTS idx_agent_runs_created ON agent_runs (created_at);
