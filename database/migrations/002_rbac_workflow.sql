-- ============================================================
-- IR-ABPS / Railway Block Optimizer
-- RBAC Workflow & Audit Trail Migration (Additive Only)
-- ============================================================

BEGIN;

-- ============================================================
-- 1. BLOCK REVIEW EVENTS TABLE
-- ============================================================

CREATE TABLE IF NOT EXISTS block_review_events (
    event_id BIGSERIAL PRIMARY KEY,
    block_id VARCHAR(30) NOT NULL,
    actor_role VARCHAR(30) NOT NULL,
    actor_name VARCHAR(150),
    actor_dept VARCHAR(20),
    action VARCHAR(40) NOT NULL,
    note TEXT,
    payload JSONB,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_block_review_events_block_id
    ON block_review_events(block_id);

CREATE INDEX IF NOT EXISTS idx_block_review_events_created_at
    ON block_review_events(created_at);

-- ============================================================
-- 2. AUDIT LOG TABLE
-- ============================================================

CREATE TABLE IF NOT EXISTS audit_log (
    audit_id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    actor_role VARCHAR(30),
    actor_name VARCHAR(150),
    method VARCHAR(10),
    path TEXT,
    action VARCHAR(60),
    target_type VARCHAR(40),
    target_id VARCHAR(60),
    outcome VARCHAR(10),
    detail JSONB
);

CREATE INDEX IF NOT EXISTS idx_audit_log_ts
    ON audit_log(ts);

CREATE INDEX IF NOT EXISTS idx_audit_log_actor_role
    ON audit_log(actor_role);

CREATE INDEX IF NOT EXISTS idx_audit_log_action
    ON audit_log(action);

COMMIT;
