-- ============================================
-- 7. USEFUL VIEWS (Optional)
-- ============================================

-- View for active harvest endpoints with repository info
CREATE OR REPLACE VIEW v_active_harvest_endpoints AS
SELECT
    e.id as endpoint_id,
    e.name as endpoint_name,
    e.harvest_url,
    e.protocol,
    e.scientific_discipline,
    r.name as repository_name,
    r.code as repository_code,
    r.base_url as repository_url
FROM endpoints e
JOIN repositories r ON e.repository_id = r.id
WHERE e.is_active = true AND r.is_active = true;

-- View for harvest events summary
CREATE OR REPLACE VIEW v_harvest_events_summary AS
SELECT
    e.name as endpoint_name,
    r.name as repository_name,
    COUNT(*) as event_count
FROM harvest_events he
JOIN endpoints e ON he.endpoint_id = e.id
JOIN repositories r ON he.repository_id = r.id
GROUP BY e.name, r.name;

-- View for records statistics
CREATE OR REPLACE VIEW v_records_statistics AS
SELECT
    r.name as repository_name,
    e.name as endpoint_name,
    rec.resource_type,
    COUNT(*) as record_count,
    COUNT(DISTINCT rec.doi) as unique_dois,
    COUNT(CASE WHEN rec.opensearch_synced THEN 1 END) as synced_count,
    MAX(rec.updated_at) as last_updated
FROM records rec
JOIN endpoints e ON rec.endpoint_id = e.id
JOIN repositories r ON rec.repository_id = r.id
GROUP BY r.name, e.name, rec.resource_type;
