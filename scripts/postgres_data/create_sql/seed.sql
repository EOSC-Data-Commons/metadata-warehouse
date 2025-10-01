-- ============================================
-- 6. SAMPLE DATA
-- ============================================

-- Sample repository
INSERT INTO repositories (name, code, description, base_url, is_active)
VALUES
    ('Data Archiving and Networked Services', 'DANS', 'Dutch national archive for research data', 'https://dans.knaw.nl', true),
    ('Digital Academic Repository', 'DABAR', 'Croatian national repository', 'https://dabar.srce.hr', true),
    ('SwissUbase', 'SWISS', 'Swiss data repository', 'https://www.swissubase.ch', true),
    ('HAL Science', 'HAL', 'French open archive', 'https://hal.science', true)
ON CONFLICT (code) DO NOTHING;

-- Sample endpoint
INSERT INTO endpoints (repository_id, name, harvest_url, protocol, scientific_discipline, is_active)
SELECT
    r.id,
    'DANS Easy Dataset Archive',
    'https://easy.dans.knaw.nl/oai',
    'OAI-PMH',
    'Multidisciplinary',
    true
FROM repositories r
WHERE r.code = 'DANS'
ON CONFLICT (name) DO NOTHING;
