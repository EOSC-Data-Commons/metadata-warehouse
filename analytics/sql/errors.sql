SELECT he.*, hr.*, e.name AS endpoint_name
FROM harvest_events he
JOIN harvest_runs hr ON he.harvest_run_id = hr.id
JOIN endpoints e ON he.endpoint_id = e.id
WHERE he.error_message IS NOT NULL;
