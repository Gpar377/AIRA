-- =============================================================================
-- AIRA Unified PostgreSQL Schema
-- Defines all tables for both SentinelArena (autonomous security)
-- and NeuralOps (autonomous reliability and healing).
-- =============================================================================

-- Enable extension for JSON processing if needed (PostgreSQL has JSONB natively)

-- ─────────────────────────────────────────────────────────────────────────────
-- Part 1: SentinelArena Tables (Autonomous Security Security Operations)
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS arena_runs (
    id VARCHAR(50) PRIMARY KEY,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (now() AT TIME ZONE 'UTC') NOT NULL,
    source VARCHAR(50) DEFAULT 'live_ollama' NOT NULL,
    
    -- Learnings and aggregates (JSON arrays)
    red_learned JSONB DEFAULT '[]'::jsonb NOT NULL,
    blue_learned JSONB DEFAULT '[]'::jsonb NOT NULL,
    patched_resources JSONB DEFAULT '[]'::jsonb NOT NULL,
    attempted_attacks JSONB DEFAULT '[]'::jsonb NOT NULL,
    successful_attacks JSONB DEFAULT '[]'::jsonb NOT NULL,
    
    -- Score tracker
    score_timeline JSONB DEFAULT '[]'::jsonb NOT NULL
);

CREATE TABLE IF NOT EXISTS battle_rounds (
    id SERIAL PRIMARY KEY,
    arena_id VARCHAR(50) NOT NULL REFERENCES arena_runs(id) ON DELETE CASCADE,
    round_number INTEGER NOT NULL,
    timestamp TIMESTAMP WITHOUT TIME ZONE DEFAULT (now() AT TIME ZONE 'UTC') NOT NULL,
    source VARCHAR(50) DEFAULT 'live_ollama' NOT NULL,
    
    -- Attack agent fields
    attack_type VARCHAR(100),
    attack_target VARCHAR(255),
    attack_method TEXT,
    attack_outcome VARCHAR(50),
    
    -- Policy gate
    opa_decision VARCHAR(50),
    
    -- Defense agent fields
    defense_type VARCHAR(100),
    defense_target VARCHAR(255),
    defense_method TEXT,
    defense_outcome VARCHAR(50),
    defense_score_delta DOUBLE PRECISION DEFAULT 0.0,
    
    -- Round surface metrics
    score_before DOUBLE PRECISION,
    score_after DOUBLE PRECISION,
    score_delta DOUBLE PRECISION
);

-- Indexing for fast round queries by arena session
CREATE INDEX IF NOT EXISTS idx_battle_rounds_arena_id ON battle_rounds(arena_id);


-- ─────────────────────────────────────────────────────────────────────────────
-- Part 2: NeuralOps Tables (Autonomous Reliability Operations)
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS incidents (
    id SERIAL PRIMARY KEY,
    
    -- Prediction engine fields
    failure_type VARCHAR(50) NOT NULL,
    predicted_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (now() AT TIME ZONE 'UTC') NOT NULL,
    predicted_time_to_failure_minutes DOUBLE PRECISION,
    confidence_score DOUBLE PRECISION NOT NULL,
    
    -- Target system coordinates
    namespace VARCHAR(100) NOT NULL,
    pod_name VARCHAR(255),
    deployment_name VARCHAR(255),
    service_name VARCHAR(255),
    
    -- Target metrics state (features array JSON)
    metrics_snapshot JSONB,
    
    -- Cause and Diagnostic analysis
    root_cause TEXT,
    diagnosis_completed_at TIMESTAMP WITHOUT TIME ZONE,
    
    -- Tracing and logs aggregated
    relevant_logs JSONB,
    trace_ids JSONB,
    
    -- Healing actions executed
    remediation_action VARCHAR(100),
    remediation_executed_at TIMESTAMP WITHOUT TIME ZONE,
    remediation_successful BOOLEAN,
    remediation_details JSONB,
    
    -- Autonomy level tiering
    autonomy_level VARCHAR(20),  -- TIER_1, TIER_2, TIER_3
    human_approved BOOLEAN DEFAULT FALSE,
    
    -- Results tracking
    resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMP WITHOUT TIME ZONE,
    actual_failure_occurred BOOLEAN
);

CREATE INDEX IF NOT EXISTS idx_incidents_failure_type ON incidents(failure_type);
CREATE INDEX IF NOT EXISTS idx_incidents_resolved ON incidents(resolved);


CREATE TABLE IF NOT EXISTS similar_incidents (
    id SERIAL PRIMARY KEY,
    incident_id INTEGER NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    similar_incident_id INTEGER NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    similarity_score DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_similar_incidents_incident_id ON similar_incidents(incident_id);


CREATE TABLE IF NOT EXISTS remediation_actions (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    action_type VARCHAR(50) NOT NULL,  -- restart, scale, rollback, etc.
    
    -- Success rate stats
    times_used INTEGER DEFAULT 0,
    times_successful INTEGER DEFAULT 0
);


CREATE TABLE IF NOT EXISTS agent_reasoning (
    id SERIAL PRIMARY KEY,
    incident_id INTEGER NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    
    step_number INTEGER NOT NULL,
    node_name VARCHAR(50) NOT NULL,  -- predict, diagnose, decide, heal, remember
    
    input_data JSONB,
    output_data JSONB,
    reasoning TEXT,
    
    started_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (now() AT TIME ZONE 'UTC'),
    completed_at TIMESTAMP WITHOUT TIME ZONE,
    duration_seconds DOUBLE PRECISION
);

CREATE INDEX IF NOT EXISTS idx_agent_reasoning_incident_id ON agent_reasoning(incident_id);
