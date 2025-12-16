-- ---------------------------
-- DATABASE 3 – Tool Registry, connect to toolDB first
-- ---------------------------
/c toolDB
-- Create roles
CREATE ROLE toolDB__read;
CREATE ROLE toolDB__readwrite;
CREATE ROLE toolDB__admin;

GRANT CONNECT ON DATABASE toolDB TO toolDB_read, toolDB_readwrite, toolDB_admin;

-- READ
GRANT USAGE ON SCHEMA public TO toolDB_read;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO toolDB_read;

-- READWRITE
GRANT USAGE, CREATE ON SCHEMA public TO toolDB_readwrite;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES TO toolDB_readwrite;

-- ADMIN
GRANT ALL PRIVILEGES ON DATABASE toolDB TO toolDB_admin;
GRANT ALL PRIVILEGES ON SCHEMA public TO toolDB_admin;
GRANT ALL PRIVILEGES ON ALL TABLES TO toolDB_admin;

-- Future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT SELECT ON TABLES TO toolDB_read;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT SELECT, INSERT, UPDATE ON TABLES TO toolDB_readwrite;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT ALL ON TABLES TO toolDB_admin;

-- Read
GRANT toolDB__read TO tobias, josip, ping, vincent, ritwik;

-- Read/Write, script cannot delete important
GRANT toolDB__readwrite TO script;

-- Admin
GRANT toolDB__admin TO michal, jusong, reggie, eko;