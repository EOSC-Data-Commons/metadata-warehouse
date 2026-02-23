-- ================================
-- Tool DB RBAC Configuration
-- ================================

CREATE ROLE tooldb_read NOLOGIN;
CREATE ROLE tooldb_readwrite NOLOGIN;
CREATE ROLE tooldb_admin NOLOGIN;

GRANT CONNECT ON DATABASE tooldb TO tooldb_read, tooldb_readwrite, tooldb_admin;

-- READ
GRANT USAGE ON SCHEMA public TO tooldb_read;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO tooldb_read;

-- READWRITE
GRANT USAGE, CREATE ON SCHEMA public TO tooldb_readwrite;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO tooldb_readwrite;

-- ADMIN
GRANT ALL PRIVILEGES ON DATABASE tooldb TO tooldb_admin;
GRANT ALL PRIVILEGES ON SCHEMA public TO tooldb_admin;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO tooldb_admin;

-- Future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO tooldb_read;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE ON TABLES TO tooldb_readwrite;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO tooldb_admin;

-- Assign memberships
GRANT tooldb_read TO tobias, josip, ping, vincent, ritwik;
GRANT tooldb_readwrite TO script;
GRANT tooldb_admin TO michal, jusong, reggie, eko;
