
-- ---------------------------
-- DATABASE 4 – final DB used by the app: user search history, datasets, files, tools
-- ---------------------------
/c appDB

-- Create roles
CREATE ROLE appDB_read;
CREATE ROLE appDB_readwrite;
CREATE ROLE appDB_admin;

GRANT CONNECT ON DATABASE appDB TO appDB_read, appDB_readwrite, appDB_admin;

-- READ
GRANT USAGE ON SCHEMA public TO appDB_read;
GRANT SELECT ON ALL TABLES TO appDB_read;

-- READWRITE
GRANT USAGE, CREATE ON SCHEMA public TO appDB_readwrite;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES TO appDB_readwrite;

-- ADMIN
GRANT ALL PRIVILEGES ON DATABASE appDB TO appDB_admin;
GRANT ALL PRIVILEGES ON SCHEMA public TO appDB_admin;
GRANT ALL PRIVILEGES ON ALL TABLES TO appDB_admin;

-- Future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT SELECT ON TABLES TO appDB_read;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT SELECT, INSERT, UPDATE ON TABLES TO appDB_readwrite;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT ALL ON TABLES TO appDB_admin;

-- Read
GRANT appDB_read TO jusong, reggie, josip, tobias;

-- Read/Write, script cannot delete important
GRANT appDB_readwrite TO script;

-- Admin
GRANT appDB_admin TO michal, vincent, ritwik, ping;
