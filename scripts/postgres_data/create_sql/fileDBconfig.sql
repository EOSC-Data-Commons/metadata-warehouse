-- ================================
-- File DB RBAC Configuration
-- ================================

CREATE ROLE filedb_read NOLOGIN;
CREATE ROLE filedb_readwrite NOLOGIN;
CREATE ROLE filedb_admin NOLOGIN;

GRANT CONNECT ON DATABASE filedb TO filedb_read, filedb_readwrite, filedb_admin;

-- READ
GRANT USAGE ON SCHEMA public TO filedb_read;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO filedb_read;

-- READWRITE
GRANT USAGE, CREATE ON SCHEMA public TO filedb_readwrite;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO filedb_readwrite;

-- ADMIN
GRANT ALL PRIVILEGES ON DATABASE filedb TO filedb_admin;
GRANT ALL PRIVILEGES ON SCHEMA public TO filedb_admin;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO filedb_admin;

-- Future
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO filedb_read;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE ON TABLES TO filedb_readwrite;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO filedb_admin;

-- Assign role memberships
GRANT filedb_read TO tobias, josip, ping, vincent, ritwik;
GRANT filedb_readwrite TO script;
GRANT filedb_admin TO michal, reggie, jusong, eko;
