-- AccountabilityMe - Read Model Projection Tables
-- 
-- These tables are derived from the event log and can be rebuilt at any time.
-- They provide fast query access without scanning the entire event stream.
--
-- IMPORTANT: These are CACHES, not sources of truth.
-- The source of truth is always ledger_events.
--
-- To rebuild projections:
--   1. TRUNCATE the projection tables
--   2. Replay events from ledger_events in sequence order
--   3. Call the appropriate projection update for each event

-- ============================================================
-- CLAIMS PROJECTION
-- Denormalized view of claim state for fast queries
-- ============================================================

CREATE TABLE IF NOT EXISTS claims_projection (
    -- Primary identifier
    claim_id UUID PRIMARY KEY,
    
    -- Reference ID (human-readable, optional)
    reference_id VARCHAR(50) UNIQUE,
    
    -- Claimant who made the claim
    claimant_id UUID NOT NULL,
    
    -- The claim statement
    statement TEXT NOT NULL,
    statement_context TEXT,
    
    -- Source where claim was made
    source_url TEXT,
    
    -- Claim classification
    claim_type VARCHAR(50) NOT NULL DEFAULT 'predictive',
    
    -- Scope information (denormalized from Scope object)
    scope_geographic VARCHAR(200),
    scope_policy_domain VARCHAR(200),
    scope_affected_population VARCHAR(200),
    
    -- Current status (derived from latest event)
    status VARCHAR(50) NOT NULL DEFAULT 'declared',
    
    -- Key dates
    declared_at TIMESTAMPTZ NOT NULL,
    operationalized_at TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ,
    
    -- Operationalization details (populated when operationalized)
    outcome_description TEXT,
    metrics JSONB,  -- Array of metric strings
    direction_of_change VARCHAR(50),
    baseline_value TEXT,
    baseline_date DATE,
    evaluation_start_date DATE,
    evaluation_end_date DATE,
    tolerance_window_days INTEGER,
    success_conditions JSONB,
    
    -- Resolution details (populated when resolved)
    resolution VARCHAR(50),
    resolution_summary TEXT,
    
    -- Counts
    evidence_count INTEGER NOT NULL DEFAULT 0,
    supporting_evidence_count INTEGER NOT NULL DEFAULT 0,
    contradicting_evidence_count INTEGER NOT NULL DEFAULT 0,
    
    -- Chain integrity (for quick display)
    ledger_integrity_valid BOOLEAN NOT NULL DEFAULT TRUE,
    
    -- Event tracking
    last_event_sequence BIGINT NOT NULL,
    last_event_hash VARCHAR(64) NOT NULL,
    created_by UUID NOT NULL,
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_claims_proj_status ON claims_projection (status);
CREATE INDEX IF NOT EXISTS idx_claims_proj_claimant ON claims_projection (claimant_id);
CREATE INDEX IF NOT EXISTS idx_claims_proj_declared ON claims_projection (declared_at DESC);
CREATE INDEX IF NOT EXISTS idx_claims_proj_resolved ON claims_projection (resolved_at DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_claims_proj_type ON claims_projection (claim_type);
CREATE INDEX IF NOT EXISTS idx_claims_proj_domain ON claims_projection (scope_policy_domain);

-- Full-text search index on statement
CREATE INDEX IF NOT EXISTS idx_claims_proj_statement_search 
    ON claims_projection USING gin(to_tsvector('english', statement));

-- ============================================================
-- EDITORS PROJECTION
-- Fast lookup for editor information
-- ============================================================

CREATE TABLE IF NOT EXISTS editors_projection (
    -- Primary identifier
    editor_id UUID PRIMARY KEY,
    
    -- Editor identity
    username VARCHAR(100) NOT NULL UNIQUE,
    display_name VARCHAR(200) NOT NULL,
    role VARCHAR(50) NOT NULL,
    
    -- Cryptographic identity (IMMUTABLE after registration)
    public_key TEXT NOT NULL UNIQUE,
    
    -- Status
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    
    -- Registration info
    registered_at TIMESTAMPTZ NOT NULL,
    registered_by UUID,
    registration_rationale TEXT,
    
    -- Deactivation info (if deactivated)
    deactivated_at TIMESTAMPTZ,
    deactivated_by UUID,
    deactivation_reason TEXT,
    
    -- Activity metrics
    claim_count INTEGER NOT NULL DEFAULT 0,
    evidence_count INTEGER NOT NULL DEFAULT 0,
    last_action_at TIMESTAMPTZ,
    
    -- Event tracking
    last_event_sequence BIGINT NOT NULL,
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_editors_proj_active ON editors_projection (is_active);
CREATE INDEX IF NOT EXISTS idx_editors_proj_role ON editors_projection (role);
CREATE INDEX IF NOT EXISTS idx_editors_proj_username ON editors_projection (username);

-- ============================================================
-- EVIDENCE PROJECTION
-- Fast lookup for evidence items
-- ============================================================

CREATE TABLE IF NOT EXISTS evidence_projection (
    -- Primary identifier
    evidence_id UUID PRIMARY KEY,
    
    -- Related claim
    claim_id UUID NOT NULL REFERENCES claims_projection(claim_id),
    
    -- Source information
    source_url TEXT NOT NULL,
    source_title TEXT NOT NULL,
    source_publisher TEXT,
    source_date DATE,
    source_type VARCHAR(50) NOT NULL,
    
    -- Evidence classification
    evidence_type VARCHAR(50) NOT NULL,
    
    -- Content
    summary TEXT NOT NULL,
    supports_claim BOOLEAN NOT NULL,
    relevance_explanation TEXT,
    
    -- Quality metrics
    confidence_score DECIMAL(3,2),
    confidence_rationale TEXT,
    
    -- Editorial attribution
    added_by UUID NOT NULL,
    added_at TIMESTAMPTZ NOT NULL,
    
    -- Event tracking
    event_sequence BIGINT NOT NULL,
    event_hash VARCHAR(64) NOT NULL,
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_evidence_proj_claim ON evidence_projection (claim_id);
CREATE INDEX IF NOT EXISTS idx_evidence_proj_supports ON evidence_projection (claim_id, supports_claim);
CREATE INDEX IF NOT EXISTS idx_evidence_proj_type ON evidence_projection (evidence_type);
CREATE INDEX IF NOT EXISTS idx_evidence_proj_source_type ON evidence_projection (source_type);

-- ============================================================
-- ANCHOR BATCHES
-- Stores Merkle root anchoring information
-- ============================================================

CREATE TABLE IF NOT EXISTS anchor_batches (
    -- Primary identifier
    batch_id UUID PRIMARY KEY,
    
    -- Batch range
    start_sequence BIGINT NOT NULL,
    end_sequence BIGINT NOT NULL,
    event_count INTEGER NOT NULL,
    
    -- Merkle tree
    merkle_root VARCHAR(64) NOT NULL,
    
    -- Anchor destination (where the root was published)
    anchor_type VARCHAR(50) NOT NULL,  -- 'git_tag', 's3_versioned', 'blockchain', etc.
    anchor_reference TEXT,  -- Git tag name, S3 version ID, tx hash, etc.
    anchor_url TEXT,  -- URL to verify anchor
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    anchored_at TIMESTAMPTZ,  -- When anchor was confirmed
    
    -- Status
    status VARCHAR(50) NOT NULL DEFAULT 'pending',  -- pending, anchored, failed
    
    CONSTRAINT valid_batch_range CHECK (start_sequence <= end_sequence),
    CONSTRAINT valid_event_count CHECK (event_count = end_sequence - start_sequence + 1)
);

CREATE INDEX IF NOT EXISTS idx_anchor_batches_range ON anchor_batches (start_sequence, end_sequence);
CREATE INDEX IF NOT EXISTS idx_anchor_batches_status ON anchor_batches (status);
CREATE INDEX IF NOT EXISTS idx_anchor_batches_created ON anchor_batches (created_at DESC);

-- ============================================================
-- PROJECTION METADATA
-- Tracks projection state for rebuild operations
-- ============================================================

CREATE TABLE IF NOT EXISTS projection_metadata (
    projection_name VARCHAR(50) PRIMARY KEY,
    last_processed_sequence BIGINT NOT NULL DEFAULT -1,
    last_processed_hash VARCHAR(64),
    last_rebuild_at TIMESTAMPTZ,
    event_count INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Initialize metadata for each projection
INSERT INTO projection_metadata (projection_name, last_processed_sequence, event_count)
VALUES 
    ('claims', -1, 0),
    ('editors', -1, 0),
    ('evidence', -1, 0)
ON CONFLICT (projection_name) DO NOTHING;

-- ============================================================
-- TIMESTAMP UPDATE TRIGGER
-- ============================================================

CREATE OR REPLACE FUNCTION update_projection_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply to all projection tables
DROP TRIGGER IF EXISTS claims_projection_timestamp ON claims_projection;
CREATE TRIGGER claims_projection_timestamp
    BEFORE UPDATE ON claims_projection
    FOR EACH ROW
    EXECUTE FUNCTION update_projection_timestamp();

DROP TRIGGER IF EXISTS editors_projection_timestamp ON editors_projection;
CREATE TRIGGER editors_projection_timestamp
    BEFORE UPDATE ON editors_projection
    FOR EACH ROW
    EXECUTE FUNCTION update_projection_timestamp();

DROP TRIGGER IF EXISTS projection_metadata_timestamp ON projection_metadata;
CREATE TRIGGER projection_metadata_timestamp
    BEFORE UPDATE ON projection_metadata
    FOR EACH ROW
    EXECUTE FUNCTION update_projection_timestamp();

-- ============================================================
-- HELPER VIEWS
-- ============================================================

-- Dashboard summary view
CREATE OR REPLACE VIEW dashboard_summary AS
SELECT
    (SELECT COUNT(*) FROM claims_projection) AS total_claims,
    (SELECT COUNT(*) FROM claims_projection WHERE status = 'declared') AS declared_claims,
    (SELECT COUNT(*) FROM claims_projection WHERE status = 'operationalized') AS operationalized_claims,
    (SELECT COUNT(*) FROM claims_projection WHERE status = 'observing') AS observing_claims,
    (SELECT COUNT(*) FROM claims_projection WHERE status = 'resolved') AS resolved_claims,
    (SELECT COUNT(*) FROM editors_projection WHERE is_active = TRUE) AS active_editors,
    (SELECT COUNT(*) FROM evidence_projection) AS total_evidence,
    (SELECT MAX(last_processed_sequence) FROM projection_metadata) AS last_sequence;

-- Claims with evidence counts view
CREATE OR REPLACE VIEW claims_with_evidence AS
SELECT 
    c.*,
    COALESCE(e.supporting, 0) AS calc_supporting_evidence,
    COALESCE(e.contradicting, 0) AS calc_contradicting_evidence
FROM claims_projection c
LEFT JOIN (
    SELECT 
        claim_id,
        SUM(CASE WHEN supports_claim THEN 1 ELSE 0 END) AS supporting,
        SUM(CASE WHEN NOT supports_claim THEN 1 ELSE 0 END) AS contradicting
    FROM evidence_projection
    GROUP BY claim_id
) e ON c.claim_id = e.claim_id;
