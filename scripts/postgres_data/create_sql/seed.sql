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

-- DANS Archaeology
INSERT INTO endpoints (repository_id, name, code, harvest_url, protocol, scientific_discipline, is_active, harvest_params)
SELECT
    r.id,
    'Archaeology Data Station',
    'arch',
    'https://archaeology.datastations.nl/oai',
    'OAI-PMH',
    'Multidisciplinary',
    true,
    '{"metadata_prefix": "oai_datacite"}'
FROM repositories r
WHERE r.code = 'DANS'
ON CONFLICT (name) DO NOTHING;

-- DANS Social Sciences Data Station
INSERT INTO endpoints (repository_id, name, code, harvest_url, protocol, scientific_discipline, is_active, harvest_params)
SELECT
    r.id,
    'Social Sciences Data Station',
    'soc',
    'https://ssh.datastations.nl/oai',
    'OAI-PMH',
    'Multidisciplinary',
    true,
    '{"metadata_prefix": "oai_datacite"}'
FROM repositories r
WHERE r.code = 'DANS'
ON CONFLICT (name) DO NOTHING;

-- DANS Life Sciences
INSERT INTO endpoints (repository_id, name, code, harvest_url, protocol, scientific_discipline, is_active, harvest_params)
SELECT
    r.id,
    'Life Sciences',
    'life',
    'https://lifesciences.datastations.nl/oai',
    'OAI-PMH',
    'Multidisciplinary',
    true,
    '{"metadata_prefix": "oai_datacite"}'
FROM repositories r
WHERE r.code = 'DANS'
ON CONFLICT (name) DO NOTHING;

-- DANS Physical and Technical Sciences
INSERT INTO endpoints (repository_id, name, code, harvest_url, protocol, scientific_discipline, is_active, harvest_params)
SELECT
    r.id,
    'Physical and Technical Sciences',
    'phystech',
    'https://phys-techsciences.datastations.nl/oai',
    'OAI-PMH',
    'Multidisciplinary',
    true,
    '{"metadata_prefix": "oai_datacite"}'
FROM repositories r
WHERE r.code = 'DANS'
ON CONFLICT (name) DO NOTHING;

-- DANS Generalist
INSERT INTO endpoints (repository_id, name, code, harvest_url, protocol, scientific_discipline, is_active, harvest_params)
SELECT
    r.id,
    'Generalist',
    'gen',
    'https://dataverse.nl/oai',
    'OAI-PMH',
    'Multidisciplinary',
    true,
    '{"metadata_prefix": "oai_datacite"}'
FROM repositories r
WHERE r.code = 'DANS'
ON CONFLICT (name) DO NOTHING;

-- SwissUbase
INSERT INTO endpoints (repository_id, name, code, harvest_url, protocol, scientific_discipline, is_active, harvest_params)
SELECT
    r.id,
    'SwissUbase',
    'swiss',
    'https://www.swissubase.ch/oai-pmh/v1/oai',
    'OAI-PMH',
    'Multidisciplinary',
    true,
    '{"metadata_prefix": "oai_ddi25"}'
FROM repositories r
WHERE r.code = 'SWISS'
ON CONFLICT (name) DO NOTHING;

-- DABAR
INSERT INTO endpoints (repository_id, name, code, harvest_url, protocol, scientific_discipline, is_active, harvest_params)
SELECT
    r.id,
    'DABAR',
    'dabar',
    'https://dabar.srce.hr/oai',
    'OAI-PMH',
    'Multidisciplinary',
    true,
    '{"metadata_prefix": "oai_datacite", "set": "openaire_data"}'
FROM repositories r
WHERE r.code = 'DABAR'
ON CONFLICT (name) DO NOTHING;

-- HAL
INSERT INTO endpoints (repository_id, name, code, harvest_url, protocol, scientific_discipline, is_active, harvest_params)
SELECT
    r.id,
    'HAL',
    'hal',
    'https://api.archives-ouvertes.fr/oai/hal',
    'OAI-PMH',
    'Multidisciplinary',
    true,
    '{"metadata_prefix": "oai_datacite"}'
FROM repositories r
WHERE r.code = 'HAL'
ON CONFLICT (name) DO NOTHING;
