-- ============================================
-- 9 verify installation
-- ============================================

--
SELECT
    'Tables created' as status,
    COUNT(*) as count
FROM information_schema.tables
WHERE table_schema = 'public'
    AND table_name IN ('repositories', 'endpoints', 'harvest_events', 'records', 'harvest_runs');

SELECT
    'Custom types created' as status,
    COUNT(*) as count
FROM pg_type t
JOIN pg_namespace n ON t.typnamespace = n.oid
WHERE n.nspname = 'public'
    AND t.typname IN ('harvest_protocol', 'resource_type', 'event_action', 'event_status', 'content_format');
