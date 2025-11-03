-- ============================================
-- 4. INDEXES
-- ============================================

-- Repositories Indexes
CREATE INDEX IF NOT EXISTS idx_repositories_code ON repositories(code);
CREATE INDEX IF NOT EXISTS idx_repositories_is_active ON repositories(is_active) WHERE is_active = true;

-- Endpoints Indexes
CREATE INDEX IF NOT EXISTS idx_endpoints_repository_id ON endpoints(repository_id);
CREATE INDEX IF NOT EXISTS idx_endpoints_protocol ON endpoints(protocol);
CREATE INDEX IF NOT EXISTS idx_endpoints_is_active ON endpoints(is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_endpoints_next_scheduled_harvest ON endpoints(next_scheduled_harvest) WHERE is_active = true;

-- Harvest Events Indexes
CREATE INDEX IF NOT EXISTS idx_harvest_events_repository_id ON harvest_events(repository_id);
CREATE INDEX IF NOT EXISTS idx_harvest_events_endpoint_id ON harvest_events(endpoint_id);
CREATE INDEX IF NOT EXISTS idx_harvest_events_record_identifier ON harvest_events(record_identifier);
CREATE INDEX IF NOT EXISTS idx_harvest_events_status ON harvest_events(status);
CREATE INDEX IF NOT EXISTS idx_harvest_events_harvested_at ON harvest_events(harvested_at);
CREATE INDEX IF NOT EXISTS idx_harvest_events_processed_at ON harvest_events(processed_at) WHERE processed_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_harvest_events_status_harvested_at ON harvest_events(status, harvested_at) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_harvest_events_endpoint_record_harvested ON harvest_events(endpoint_id, record_identifier, harvested_at);

-- Records Indexes
CREATE INDEX IF NOT EXISTS idx_records_endpoint_id ON records(endpoint_id);
CREATE INDEX IF NOT EXISTS idx_records_repository_id ON records(repository_id);
CREATE INDEX IF NOT EXISTS idx_records_record_identifier ON records(record_identifier);
CREATE INDEX IF NOT EXISTS idx_records_resource_type ON records(resource_type);
CREATE INDEX IF NOT EXISTS idx_records_doi ON records(doi) WHERE doi IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_records_deleted_at ON records(deleted_at) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_records_opensearch_synced ON records(opensearch_synced) WHERE opensearch_synced = false;
CREATE INDEX IF NOT EXISTS idx_records_created_at ON records USING brin(created_at);
CREATE INDEX IF NOT EXISTS idx_records_updated_at ON records USING brin(updated_at);
CREATE INDEX IF NOT EXISTS idx_records_datacite_json ON records USING gin(datacite_json);
CREATE INDEX IF NOT EXISTS idx_records_title_fulltext ON records USING gin(to_tsvector('english', title));

-- Harvest Runs Indexes
CREATE INDEX IF NOT EXISTS idx_harvest_runs_endpoint_id ON harvest_runs(endpoint_id);
CREATE INDEX IF NOT EXISTS idx_harvest_runs_started_at ON harvest_runs(started_at);
CREATE INDEX IF NOT EXISTS idx_harvest_runs_status ON harvest_runs(status);
