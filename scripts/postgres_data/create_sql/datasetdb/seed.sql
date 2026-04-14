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
    ('Zenodo', 'ZENODO', 'Zenodo repository', 'https://zenodo.org', true),
    ('PaNOSC', 'PANOSC', 'Scientific data infrastructure repository', 'https://www.panosc.eu/', true)
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
    '{"metadata_prefix": "oai_datacite", "additional_metadata_params": {"endpoint": "https://archaeology.datastations.nl/api/datasets/:persistentId/versions/:latest-published", "protocol": "REST_API", "format": "dataverse_json"}}',
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
    '{"metadata_prefix": "oai_datacite", "additional_metadata_params": {"endpoint": "https://ssh.datastations.nl/api/datasets/:persistentId/versions/:latest-published", "protocol": "REST_API", "format": "dataverse_json"}}',
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
    '{"metadata_prefix": "oai_datacite", "additional_metadata_params": {"endpoint": "https://lifesciences.datastations.nl/api/datasets/:persistentId/versions/:latest-published", "protocol": "REST_API", "format": "dataverse_json"}}',
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
    '{"metadata_prefix": "oai_datacite", "additional_metadata_params": {"endpoint": "https://phys-techsciences.datastations.nl/api/datasets/:persistentId/versions/:latest-published", "protocol": "REST_API", "format": "dataverse_json"}}',
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
    '{"metadata_prefix": "oai_datacite", "additional_metadata_params": {"endpoint": "https://dataverse.nl/api/datasets/:persistentId/versions/:latest-published", "protocol": "REST_API", "format": "dataverse_json"}}',
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
    '{"metadata_prefix": "oai_datacite", "set": ["collection:LINKED_RESEARCH_OUTPUTS"]}',
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


-- PaNOSc DESY
INSERT INTO endpoints (repository_id, name, harvest_url, protocol, scientific_discipline, is_active, harvest_params, harvest_schedule)
SELECT
    r.id,
    'DESY',
    'https://public-data.desy.de/oaipmh/oai',
    'OAI-PMH',
    'Multidisciplinary',
    true,
    '{"metadata_prefix": "oai_dc"}',
    INTERVAL '1 week'
FROM repositories r
WHERE r.code = 'PaNOSc'
ON CONFLICT (name) DO NOTHING;


-- PaNOSc Elettra
INSERT INTO endpoints (repository_id, name, harvest_url, protocol, scientific_discipline, is_active, harvest_params, harvest_schedule)
SELECT
    r.id,
    'Elettra',
    'https://api.opendata.elettra.eu/oaipmh/',
    'OAI-PMH',
    'Multidisciplinary',
    true,
    '{"metadata_prefix": "oai_dc"}',
    INTERVAL '1 week'
FROM repositories r
WHERE r.code = 'PaNOSc'
ON CONFLICT (name) DO NOTHING;


-- PaNOSc ESRF
INSERT INTO endpoints (repository_id, name, harvest_url, protocol, scientific_discipline, is_active, harvest_params, harvest_schedule)
SELECT
    r.id,
    'ESRF',
    'https://icatplus.esrf.fr/oaipmh/request',
    'OAI-PMH',
    'Multidisciplinary',
    true,
    '{"metadata_prefix": "oai_datacite"}',
    INTERVAL '1 week'
FROM repositories r
WHERE r.code = 'PaNOSc'
ON CONFLICT (name) DO NOTHING;


-- PaNOSc ESS
INSERT INTO endpoints (repository_id, name, harvest_url, protocol, scientific_discipline, is_active, harvest_params, harvest_schedule)
SELECT
    r.id,
    'ESS',
    'https://oai.panosc.ess.eu/openaire/oai',
    'OAI-PMH',
    'Multidisciplinary',
    true,
    '{"metadata_prefix": "oai_datacite"}',
    INTERVAL '1 week'
FROM repositories r
WHERE r.code = 'PaNOSc'
ON CONFLICT (name) DO NOTHING;


-- PaNOSc EuXFEL
INSERT INTO endpoints (repository_id, name, harvest_url, protocol, scientific_discipline, is_active, harvest_params, harvest_schedule)
SELECT
    r.id,
    'EuXFEL',
    'https://in.xfel.eu/metadata/oai-pmh/oai2',
    'OAI-PMH',
    'Multidisciplinary',
    true,
    '{"metadata_prefix": "oai_datacite"}',
    INTERVAL '1 week'
FROM repositories r
WHERE r.code = 'PaNOSc'
ON CONFLICT (name) DO NOTHING;


-- PaNOSc HZB
INSERT INTO endpoints (repository_id, name, harvest_url, protocol, scientific_discipline, is_active, harvest_params, harvest_schedule)
SELECT
    r.id,
    'HZB',
    'https://data.helmholtz-berlin.de/oaipmh/request',
    'OAI-PMH',
    'Multidisciplinary',
    true,
    '{"metadata_prefix": "oai_datacite"}',
    INTERVAL '1 week'
FROM repositories r
WHERE r.code = 'PaNOSc'
ON CONFLICT (name) DO NOTHING;


-- PaNOSc HZDR
INSERT INTO endpoints (repository_id, name, harvest_url, protocol, scientific_discipline, is_active, harvest_params, harvest_schedule)
SELECT
    r.id,
    'HZDR',
    'https://rodare.hzdr.de/oai2d',
    'OAI-PMH',
    'Multidisciplinary',
    true,
    '{"metadata_prefix": "oai_datacite", "set": ["openaire_data"]}',
    INTERVAL '1 week'
FROM repositories r
WHERE r.code = 'PaNOSc'
ON CONFLICT (name) DO NOTHING;


-- PaNOSc ILL
INSERT INTO endpoints (repository_id, name, harvest_url, protocol, scientific_discipline, is_active, harvest_params, harvest_schedule)
SELECT
    r.id,
    'ILL',
    'https://fairdata.ill.fr/openaire/oai',
    'OAI-PMH',
    'Multidisciplinary',
    true,
    '{"metadata_prefix": "oai_datacite"}',
    INTERVAL '1 week'
FROM repositories r
WHERE r.code = 'PaNOSc'
ON CONFLICT (name) DO NOTHING;


-- PaNOSc ISIS
INSERT INTO endpoints (repository_id, name, harvest_url, protocol, scientific_discipline, is_active, harvest_params, harvest_schedule)
SELECT
    r.id,
    'ISIS',
    'https://icat.isis.stfc.ac.uk/oaipmh/request',
    'OAI-PMH',
    'Multidisciplinary',
    true,
    '{"metadata_prefix": "oai_datacite"}',
    INTERVAL '1 week'
FROM repositories r
WHERE r.code = 'PaNOSc'
ON CONFLICT (name) DO NOTHING;


-- PaNOSc MAX IV
INSERT INTO endpoints (repository_id, name, harvest_url, protocol, scientific_discipline, is_active, harvest_params, harvest_schedule)
SELECT
    r.id,
    'MAX IV',
    'https://scicat.maxiv.lu.se/openaire/oai',
    'OAI-PMH',
    'Multidisciplinary',
    true,
    '{"metadata_prefix": "oai_datacite"}',
    INTERVAL '1 week'
FROM repositories r
WHERE r.code = 'PaNOSc'
ON CONFLICT (name) DO NOTHING;


-- PaNOSc PSI
INSERT INTO endpoints (repository_id, name, harvest_url, protocol, scientific_discipline, is_active, harvest_params, harvest_schedule)
SELECT
    r.id,
    'PSI',
    'https://doi.psi.ch/oaipmh/oai',
    'OAI-PMH',
    'Multidisciplinary',
    true,
    '{"metadata_prefix": "oai_dc"}',
    INTERVAL '1 week'
FROM repositories r
WHERE r.code = 'PaNOSc'
ON CONFLICT (name) DO NOTHING;