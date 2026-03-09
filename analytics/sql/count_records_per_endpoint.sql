SELECT
    e.name AS endpoint_name,
    COUNT(r.id) AS record_count
FROM records r
JOIN endpoints e ON r.endpoint_id = e.id
GROUP BY e.name
ORDER BY record_count DESC;
