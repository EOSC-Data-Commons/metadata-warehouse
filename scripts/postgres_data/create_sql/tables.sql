-- ============================================
-- Metadata Harvesting ETL Pipeline PostgreSQL Schema
-- Version: 1.0
-- ============================================

-- Drop schema if exists (be careful in production!)
-- DROP SCHEMA IF EXISTS metadata_harvest_db CASCADE;
-- CREATE SCHEMA metadata_harvest_db;
-- SET search_path TO metadata_harvest_db;

-- ============================================
-- 1. EXTENSIONS
-- ============================================
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============================================
-- 3. TABLES
-- ============================================

-- Repositories Table
CREATE TABLE IF NOT EXISTS repositories (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    code VARCHAR(50) NOT NULL UNIQUE,
    description TEXT,
    base_url VARCHAR(500),
    contact_info JSONB,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN NOT NULL DEFAULT true,
    CONSTRAINT repositories_pkey PRIMARY KEY (id),
    CONSTRAINT repositories_name_key UNIQUE (name),
    CONSTRAINT repositories_code_key UNIQUE (code)
);

COMMENT ON TABLE repositories IS 'Stores information about data repositories (DANS, DABAR, etc.)';
COMMENT ON COLUMN repositories.name IS 'Repository full name';
COMMENT ON COLUMN repositories.code IS 'Short code: DANS, DABAR, SwissUbase, HAL';
COMMENT ON COLUMN repositories.contact_info IS 'Contact details in JSON format';
COMMENT ON COLUMN repositories.metadata IS 'Additional repository-specific metadata';

-- Endpoints Table
CREATE TABLE IF NOT EXISTS endpoints (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    repository_id UUID NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    harvest_url VARCHAR(500) NOT NULL UNIQUE,
    protocol harvest_protocol NOT NULL DEFAULT 'OAI-PMH',
    scientific_discipline VARCHAR(255),
    harvest_params JSONB NOT NULL,
    harvest_schedule JSONB,
    last_harvest_date TIMESTAMP WITH TIME ZONE,
    next_scheduled_harvest TIMESTAMP WITH TIME ZONE,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN NOT NULL DEFAULT true,
    CONSTRAINT endpoints_pkey PRIMARY KEY (id),
    CONSTRAINT endpoints_name_key UNIQUE (name),
    CONSTRAINT endpoints_repository_id_name_key UNIQUE (repository_id, name),
    CONSTRAINT endpoints_repository_id_fkey FOREIGN KEY (repository_id)
        REFERENCES repositories(id) ON DELETE CASCADE
);

COMMENT ON TABLE endpoints IS 'Harvesting endpoints for repositories (multiple per repo)';
COMMENT ON COLUMN endpoints.name IS 'Endpoint name/identifier';
COMMENT ON COLUMN endpoints.harvest_url IS 'URL for harvesting data';
COMMENT ON COLUMN endpoints.protocol IS 'Primary harvest protocol';
COMMENT ON COLUMN endpoints.scientific_discipline IS 'e.g., Agriculture, Physics';
COMMENT ON COLUMN endpoints.harvest_params IS 'API keys, auth tokens, custom headers, etc.';
COMMENT ON COLUMN endpoints.harvest_schedule IS 'Cron expression and scheduling configuration';

-- Harvest Events Table
CREATE TABLE IF NOT EXISTS harvest_events (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    repository_id UUID NOT NULL,
    endpoint_id UUID NOT NULL,
    record_identifier VARCHAR(255) NOT NULL,
    action event_action NOT NULL,
    status event_status NOT NULL DEFAULT 'pending',
    raw_metadata XML NOT NULL,
    metadata_format content_format NOT NULL DEFAULT 'XML',
    metadata_protocol harvest_protocol NOT NULL,
    additional_metadata JSONB,
    datestamp TIMESTAMP WITH TIME ZONE,
    harvested_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    celery_task_id VARCHAR(255),
    CONSTRAINT harvest_events_pkey PRIMARY KEY (id),
    CONSTRAINT harvest_events_repository_id_fkey FOREIGN KEY (repository_id)
        REFERENCES repositories(id) ON DELETE CASCADE,
    CONSTRAINT harvest_events_endpoint_id_fkey FOREIGN KEY (endpoint_id)
        REFERENCES endpoints(id) ON DELETE CASCADE
);

COMMENT ON TABLE harvest_events IS 'Queue of harvested metadata events awaiting transformation';
COMMENT ON COLUMN harvest_events.record_identifier IS 'OAI-PMH identifier or unique record ID';
COMMENT ON COLUMN harvest_events.action IS 'create/update/delete';
COMMENT ON COLUMN harvest_events.status IS 'Processing status';
COMMENT ON COLUMN harvest_events.raw_metadata IS 'Original harvested metadata (XML, JSON, etc.)';
COMMENT ON COLUMN harvest_events.metadata_format IS 'Format of the raw metadata';
COMMENT ON COLUMN harvest_events.metadata_protocol IS 'Protocol used to harvest this event';
COMMENT ON COLUMN harvest_events.additional_metadata IS 'Additional metadata from REST APIs etc., includes source protocol';
COMMENT ON COLUMN harvest_events.datestamp IS 'Record datestamp from OAI-PMH header';
COMMENT ON COLUMN harvest_events.harvested_at IS 'When this event was harvested';
COMMENT ON COLUMN harvest_events.processed_at IS 'When this event was processed by transformer';
COMMENT ON COLUMN harvest_events.error_message IS 'Error details if processing failed';
COMMENT ON COLUMN harvest_events.retry_count IS 'Number of processing attempts';
COMMENT ON COLUMN harvest_events.celery_task_id IS 'Celery task ID when sent for processing';

-- Records Table
CREATE TABLE IF NOT EXISTS records (
    id VARCHAR(510) NOT NULL DEFAULT gen_random_uuid(),
    endpoint_id UUID NOT NULL,
    repository_id UUID NOT NULL,
    record_identifier VARCHAR(255) NOT NULL,
    resource_type resource_type NOT NULL,
    doi VARCHAR(255),
    url VARCHAR(2048),
    title TEXT NOT NULL,
    raw_metadata TEXT NOT NULL,
    metadata_format content_format NOT NULL DEFAULT 'XML',
    metadata_protocol harvest_protocol NOT NULL,
    datacite_json JSONB,
    additional_metadata JSONB,
    embeddings FLOAT8[],
    embedding_model VARCHAR(100),
    datestamp TIMESTAMP WITH TIME ZONE,
    version INTEGER NOT NULL DEFAULT 1,
    opensearch_synced BOOLEAN NOT NULL DEFAULT false,
    opensearch_synced_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT records_pkey PRIMARY KEY (id),
    CONSTRAINT records_endpoint_id_record_identifier_key UNIQUE (endpoint_id, record_identifier),
    CONSTRAINT records_doi_or_url_check CHECK (doi IS NOT NULL OR url IS NOT NULL),
    CONSTRAINT records_endpoint_id_fkey FOREIGN KEY (endpoint_id)
        REFERENCES endpoints(id) ON DELETE CASCADE,
    CONSTRAINT records_repository_id_fkey FOREIGN KEY (repository_id)
        REFERENCES repositories(id) ON DELETE CASCADE
);

COMMENT ON TABLE records IS 'Core harvested records - contains transformed data';
COMMENT ON COLUMN records.id IS 'Composite: endpoint_id::record_identifier';
COMMENT ON COLUMN records.repository_id IS 'Denormalized for query performance';
COMMENT ON COLUMN records.record_identifier IS 'OAI-PMH identifier or unique record ID';
COMMENT ON COLUMN records.resource_type IS 'Type of record: Dataset, JournalArticle, Software, etc.';
COMMENT ON COLUMN records.doi IS 'Digital Object Identifier';
COMMENT ON COLUMN records.url IS 'Primary URL if no DOI';
COMMENT ON COLUMN records.title IS 'Record title';
COMMENT ON COLUMN records.raw_metadata IS 'Original harvested metadata (XML, JSON, etc.)';
COMMENT ON COLUMN records.metadata_format IS 'Format of the raw metadata';
COMMENT ON COLUMN records.metadata_protocol IS 'Protocol used to harvest this record';
COMMENT ON COLUMN records.datacite_json IS 'Processed DataCite JSON';
COMMENT ON COLUMN records.additional_metadata IS 'Additional metadata from REST APIs, etc.';
COMMENT ON COLUMN records.embeddings IS 'Vector embeddings array for storage (search happens in OpenSearch)';
COMMENT ON COLUMN records.embedding_model IS 'Model used for embeddings';
COMMENT ON COLUMN records.datestamp IS 'From OAI-PMH header';
COMMENT ON COLUMN records.version IS 'Version number';
COMMENT ON COLUMN records.opensearch_synced IS 'Whether synced to OpenSearch';
COMMENT ON COLUMN records.opensearch_synced_at IS 'When last synced to OpenSearch';
COMMENT ON COLUMN records.deleted_at IS 'Soft delete timestamp';

-- Harvest Runs Table
CREATE TABLE IF NOT EXISTS harvest_runs (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    endpoint_id UUID NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE,
    status VARCHAR(50) NOT NULL,
    records_harvested INTEGER NOT NULL DEFAULT 0,
    records_created INTEGER NOT NULL DEFAULT 0,
    records_updated INTEGER NOT NULL DEFAULT 0,
    records_deleted INTEGER NOT NULL DEFAULT 0,
    errors_count INTEGER NOT NULL DEFAULT 0,
    from_date TIMESTAMP WITH TIME ZONE,
    until_date TIMESTAMP WITH TIME ZONE,
    resumption_token TEXT,
    error_log JSONB,
    CONSTRAINT harvest_runs_pkey PRIMARY KEY (id),
    CONSTRAINT harvest_runs_endpoint_id_fkey FOREIGN KEY (endpoint_id)
        REFERENCES endpoints(id) ON DELETE CASCADE
);

COMMENT ON TABLE harvest_runs IS 'Track harvest execution history';
COMMENT ON COLUMN harvest_runs.status IS 'running, completed, failed, partial';
COMMENT ON COLUMN harvest_runs.from_date IS 'Harvest from date parameter';
COMMENT ON COLUMN harvest_runs.until_date IS 'Harvest until date parameter';
COMMENT ON COLUMN harvest_runs.resumption_token IS 'OAI-PMH resumption token if interrupted';
COMMENT ON COLUMN harvest_runs.error_log IS 'Detailed error information';




