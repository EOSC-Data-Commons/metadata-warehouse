-- ================================
-- Dataset DB RBAC Configuration
-- ================================

-- Create roles
CREATE ROLE datasetdb_read NOLOGIN;
CREATE ROLE datasetdb_readwrite NOLOGIN;
CREATE ROLE datasetdb_admin NOLOGIN;

GRANT CONNECT ON DATABASE datasetdb TO datasetdb_read, datasetdb_readwrite, datasetdb_admin;

-- READ
GRANT USAGE ON SCHEMA public TO datasetdb_read;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO datasetdb_read;

-- READWRITE
GRANT USAGE, CREATE ON SCHEMA public TO datasetdb_readwrite;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO datasetdb_readwrite;

-- ADMIN
GRANT ALL PRIVILEGES ON DATABASE datasetdb TO datasetdb_admin;
GRANT ALL PRIVILEGES ON SCHEMA public TO datasetdb_admin;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO datasetdb_admin;

-- Future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO datasetdb_read;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE ON TABLES TO datasetdb_readwrite;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO datasetdb_admin;

-- Assign role memberships
GRANT datasetdb_read TO reggie, jusong, ritwik;
GRANT datasetdb_readwrite TO script;
GRANT datasetdb_admin TO tobias, josip, michal, ping, vincent;
