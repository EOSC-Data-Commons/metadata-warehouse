-- ================================
-- App DB RBAC Configuration
-- ================================

CREATE ROLE appdb_read NOLOGIN;
CREATE ROLE appdb_readwrite NOLOGIN;
CREATE ROLE appdb_admin NOLOGIN;

GRANT CONNECT ON DATABASE appdb TO appdb_read, appdb_readwrite, appdb_admin;

-- READ
GRANT USAGE ON SCHEMA public TO appdb_read;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO appdb_read;

-- READWRITE
GRANT USAGE, CREATE ON SCHEMA public TO appdb_readwrite;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO appdb_readwrite;

-- ADMIN
GRANT ALL PRIVILEGES ON DATABASE appdb TO appdb_admin;
GRANT ALL PRIVILEGES ON SCHEMA public TO appdb_admin;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO appdb_admin;

-- Future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO appdb_read;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE ON TABLES TO appdb_readwrite;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO appdb_admin;

-- Assign memberships
GRANT appdb_read TO jusong, reggie, josip, tobias;
GRANT appdb_readwrite TO script;
GRANT appdb_admin TO michal, vincent, ritwik, ping;
