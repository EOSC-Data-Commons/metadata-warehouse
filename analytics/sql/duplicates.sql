SELECT
    r.record_identifier,
    r.id AS record_id,
    e.name AS endpoint_name
FROM records r
JOIN endpoints e ON r.endpoint_id = e.id
WHERE r.record_identifier IN (
    SELECT record_identifier
    FROM records
    GROUP BY record_identifier
    HAVING COUNT(*) > 1
)
ORDER BY r.record_identifier, e.name, r.id;
