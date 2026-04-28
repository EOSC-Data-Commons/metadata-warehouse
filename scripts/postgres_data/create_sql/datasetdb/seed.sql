-- ============================================
-- 6. SAMPLE DATA
-- ============================================

-- Sample repository
INSERT INTO repositories (name, code, description, base_url, is_active)
VALUES
    ('Data Archiving and Networked Services', 'DANS', 'Dutch national archive for research data', 'https://dans.knaw.nl', true),
    ('Digital Academic Repository', 'DABAR', 'Croatian national repository', 'https://dabar.srce.hr', true),
    ('SwissUbase', 'SWISS', 'Swiss data repository', 'https://www.swissubase.ch', true),
    ('HAL Science', 'HAL', 'French open archive', 'https://hal.science', true),
    ('Onedata', 'ONE', 'Onedata demo repository', 'https://demo.onedata.org', true),
    ('FinBIF', 'FINBIF', 'Finnish Biodiversity Information Facility', 'https://laji.fi', true),
    ('Zenodo', 'ZENODO', 'Zenodo repository', 'https://zenodo.org', true)
ON CONFLICT (code) DO NOTHING;


-- DANS Archaeology
INSERT INTO endpoints (
    repository_id, name, harvest_url, protocol,
    scientific_discipline, is_active, harvest_params, harvest_schedule
)
SELECT
    r.id,
    'Archaeology Data Station',
    'https://archaeology.datastations.nl/oai',
    'OAI-PMH',
    'Multidisciplinary',
    true,
    '{"metadata_prefix": "oai_datacite", "additional_metadata_params": {"endpoint": "https://archaeology.datastations.nl/api/datasets/:persistentId/versions/:latest-published", "protocol": "DATAVERSE_API", "format": "dataverse_json"}}',
    INTERVAL '1 week'
FROM repositories r
WHERE r.code = 'DANS'
ON CONFLICT (name) DO NOTHING;


-- DANS Social Sciences Data Station
INSERT INTO endpoints (
    repository_id, name, harvest_url, protocol,
    scientific_discipline, is_active, harvest_params, harvest_schedule
)
SELECT
    r.id,
    'Social Sciences Data Station',
    'https://ssh.datastations.nl/oai',
    'OAI-PMH',
    'Multidisciplinary',
    true,
    '{"metadata_prefix": "oai_datacite", "additional_metadata_params": {"endpoint": "https://ssh.datastations.nl/api/datasets/:persistentId/versions/:latest-published", "protocol": "DATAVERSE_API", "format": "dataverse_json"}}',
    INTERVAL '1 week'
FROM repositories r
WHERE r.code = 'DANS'
ON CONFLICT (name) DO NOTHING;


-- DANS Life Sciences
INSERT INTO endpoints (
    repository_id, name, harvest_url, protocol,
    scientific_discipline, is_active, harvest_params, harvest_schedule
)
SELECT
    r.id,
    'Life Sciences',
    'https://lifesciences.datastations.nl/oai',
    'OAI-PMH',
    'Multidisciplinary',
    true,
    '{"metadata_prefix": "oai_datacite", "additional_metadata_params": {"endpoint": "https://lifesciences.datastations.nl/api/datasets/:persistentId/versions/:latest-published", "protocol": "DATAVERSE_API", "format": "dataverse_json"}}',
    INTERVAL '1 week'
FROM repositories r
WHERE r.code = 'DANS'
ON CONFLICT (name) DO NOTHING;


-- DANS Physical and Technical Sciences
INSERT INTO endpoints (
    repository_id, name, harvest_url, protocol,
    scientific_discipline, is_active, harvest_params, harvest_schedule
)
SELECT
    r.id,
    'Physical and Technical Sciences',
    'https://phys-techsciences.datastations.nl/oai',
    'OAI-PMH',
    'Multidisciplinary',
    true,
    '{"metadata_prefix": "oai_datacite", "additional_metadata_params": {"endpoint": "https://phys-techsciences.datastations.nl/api/datasets/:persistentId/versions/:latest-published", "protocol": "DATAVERSE_API", "format": "dataverse_json"}}',
    INTERVAL '1 week'
FROM repositories r
WHERE r.code = 'DANS'
ON CONFLICT (name) DO NOTHING;


-- DANS Generalist
INSERT INTO endpoints (
    repository_id, name, harvest_url, protocol,
    scientific_discipline, is_active, harvest_params, harvest_schedule
)
SELECT
    r.id,
    'Generalist',
    'https://dataverse.nl/oai',
    'OAI-PMH',
    'Multidisciplinary',
    true,
    '{"metadata_prefix": "oai_datacite", "additional_metadata_params": {"endpoint": "https://dataverse.nl/api/datasets/:persistentId/versions/:latest-published", "protocol": "DATAVERSE_API", "format": "dataverse_json"}}',
    INTERVAL '1 week'
FROM repositories r
WHERE r.code = 'DANS'
ON CONFLICT (name) DO NOTHING;


-- SwissUbase
INSERT INTO endpoints (
    repository_id, name, harvest_url, protocol,
    scientific_discipline, is_active, harvest_params, harvest_schedule
)
SELECT
    r.id,
    'SwissUbase',
    'https://www.swissubase.ch/oai-pmh/v1/oai',
    'OAI-PMH',
    'Multidisciplinary',
    true,
    '{"metadata_prefix": "oai_ddi25"}',
    INTERVAL '1 week'
FROM repositories r
WHERE r.code = 'SWISS'
ON CONFLICT (name) DO NOTHING;


-- DABAR
INSERT INTO endpoints (
    repository_id, name, harvest_url, protocol,
    scientific_discipline, is_active, harvest_params, harvest_schedule
)
SELECT
    r.id,
    'DABAR',
    'https://dabar.srce.hr/oai/',
    'OAI-PMH',
    'Multidisciplinary',
    true,
    '{"metadata_prefix": "oai_datacite", "set": ["openaire"], "additional_metadata_params": {"endpoint": "https://dabar.srce.hr/oai/", "protocol": "OAI-PMH", "format": "mods"}}',
    INTERVAL '1 week'
FROM repositories r
WHERE r.code = 'DABAR'
ON CONFLICT (name) DO NOTHING;


-- HAL
INSERT INTO endpoints (
    repository_id, name, harvest_url, protocol,
    scientific_discipline, is_active, harvest_params, harvest_schedule
)
SELECT
    r.id,
    'HAL',
    'https://api.archives-ouvertes.fr/oai/hal',
    'OAI-PMH',
    'Multidisciplinary',
    true,
    '{"metadata_prefix": "oai_datacite", "set": ["collection:LINKED_RESEARCH_OUTPUTS"], "additional_metadata_params": {"endpoint": "https://api.archives-ouvertes.fr/search/", "protocol": "HAL_API", "format": "halId_s,fileMain_s,files_s,fileType_s,modifiedDate_tdate,producedDate_tdate,version_i"}}',
    INTERVAL '1 week'
FROM repositories r
WHERE r.code = 'HAL'
ON CONFLICT (name) DO NOTHING;


-- Onedata
INSERT INTO endpoints (
    repository_id, name, harvest_url, protocol,
    scientific_discipline, is_active, harvest_params, harvest_schedule
)
SELECT
    r.id,
    'Onedata',
    'https://demo.onedata.org/oai_pmh',
    'OAI-PMH',
    'Multidisciplinary',
    true,
    '{"metadata_prefix": "oai_datacite", "set": ["a842ea97ec1855a54bf77a90e915cac7cha3ab"]}',
    INTERVAL '1 week'
FROM repositories r
WHERE r.code = 'ONE'
ON CONFLICT (name) DO NOTHING;


-- FinBIF
INSERT INTO endpoints (repository_id, name, harvest_url, protocol, scientific_discipline, is_active, harvest_params, harvest_schedule)
SELECT
    r.id,
    'FinBIF',
    'https://api.laji.fi',
    'FINBIF_API',
    'Biology',
    true,
    '{"metadata_prefix": "oai_datacite"}',
    INTERVAL '1 week'
FROM repositories r
WHERE r.code = 'FINBIF'
ON CONFLICT (name) DO NOTHING;


-- Zenodo
INSERT INTO endpoints (repository_id, name, harvest_url, protocol, scientific_discipline, is_active, harvest_params, harvest_schedule)
SELECT
    r.id,
    'Zenodo',
    'https://zenodo.org/oai2d',
    'OAI-PMH',
    'Multidisciplinary',
    false,
    '{"metadata_prefix": "datacite"}',
    INTERVAL '1 week'
FROM repositories r
WHERE r.code = 'ZENODO'
ON CONFLICT (name) DO NOTHING;
