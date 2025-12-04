SELECT
    e.name AS endpoint_name,
    COUNT(*) AS total_harvest_events,
    COUNT(*) FILTER (WHERE he.error_message IS NULL) AS without_error,
    COUNT(*) FILTER (WHERE he.error_message IS NOT NULL) AS with_error
FROM harvest_events he
JOIN harvest_runs hr ON he.harvest_run_id = hr.id
JOIN endpoints e ON he.endpoint_id = e.id
GROUP BY e.name
ORDER BY total_harvest_events DESC;
