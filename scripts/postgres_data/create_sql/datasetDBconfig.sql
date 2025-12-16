-- ---------------------------
-- DATABASE 1 – Dataset / FAIR, connect to datasetDB first
-- ---------------------------
\c datasetDB

-- Create roles
CREATE ROLE datasetDB_read;
CREATE ROLE datasetDB_readwrite;
CREATE ROLE datasetDB_admin;

GRANT CONNECT ON DATABASE datasetDB TO datasetDB_read, datasetDB_readwrite, datasetDB_admin;

-- READ
GRANT USAGE ON SCHEMA public TO datasetDB_read;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO datasetDB_read;

-- READWRITE
GRANT USAGE, CREATE ON SCHEMA public TO datasetDB_readwrite;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO datasetDB_readwrite;

-- ADMIN
GRANT ALL PRIVILEGES ON DATABASE datasetDB TO datasetDB_admin;
GRANT ALL PRIVILEGES ON SCHEMA public TO datasetDB_admin;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO datasetDB_admin;

-- Future tables inherit permissions
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT SELECT ON TABLES TO datasetDB_read;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT SELECT, INSERT, UPDATE ON TABLES TO datasetDB_readwrite;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT ALL ON TABLES TO datasetDB_admin;

-- Read
GRANT datasetDB_read TO reggie, jusong, ritwik;
-- Read/Write, script cannot delete important
GRANT datasetDB_readwrite TO script;
-- Admin
GRANT datasetDB_admin TO tobias, josip, michal, ping, vincent;