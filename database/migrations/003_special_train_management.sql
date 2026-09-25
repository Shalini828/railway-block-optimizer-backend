-- ============================================================
-- IR-ABPS / Railway Block Optimizer
-- Special Train Management Migration (Additive Only)
-- ============================================================

BEGIN;

-- ============================================================
-- 1. ADD AUDIT AND ROUTING COLUMNS TO SPECIAL_TRAIN_SERVICES
-- ============================================================

ALTER TABLE special_train_services
    ADD COLUMN IF NOT EXISTS origin_station VARCHAR(100),
    ADD COLUMN IF NOT EXISTS destination_station VARCHAR(100),
    ADD COLUMN IF NOT EXISTS created_by VARCHAR(150),
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;

-- ============================================================
-- 2. CREATE SEQUENCE FOR SPECIAL TRAIN IDS (e.g. SPL-0001)
-- ============================================================

CREATE SEQUENCE IF NOT EXISTS special_train_seq START 1;

COMMIT;
