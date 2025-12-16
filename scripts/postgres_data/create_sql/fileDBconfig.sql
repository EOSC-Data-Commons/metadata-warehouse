-- ---------------------------
-- DATABASE 2 – File Registry, connect to fileDB first
-- ---------------------------
\c fileDB

-- Create roles
CREATE ROLE fileDB_read;
CREATE ROLE fileDB_readwrite;
CREATE ROLE fileDB_admin;

GRANT CONNECT ON DATABASE fileDB TO fileDB_read, fileDB_readwrite, fileDB_admin;

-- READ
GRANT USAGE ON SCHEMA public TO fileDB_read;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO fileDB_read;

-- READWRITE
GRANT USAGE, CREATE ON SCHEMA public TO fileDB_readwrite;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES TO fileDB_readwrite;

-- ADMIN
GRANT ALL PRIVILEGES ON DATABASE fileDB TO fileDB_admin;
GRANT ALL PRIVILEGES ON SCHEMA public TO fileDB_admin;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO fileDB_admin;

-- Future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT SELECT ON TABLES TO fileDB_read;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT SELECT, INSERT, UPDATE ON TABLES TO fileDB_readwrite;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT ALL ON TABLES TO fileDB_admin;

-- Read
GRANT fileDB_read TO tobias, josip, ping, vincent, ritwik;

-- Read/Write, script cannot delete important
GRANT fileDB_readwrite TO script;

-- Admin
GRANT fileDB_admin TO michal, reggie, jusong, eko;