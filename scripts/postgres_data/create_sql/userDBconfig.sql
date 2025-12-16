
-- ---------------------------
-- DATABASE 4 – User History, connect to userDB first
-- ---------------------------
/c userDB

-- Create roles
CREATE ROLE userDB_read;
CREATE ROLE userDB_readwrite;
CREATE ROLE userDB_admin;

GRANT CONNECT ON DATABASE userDB TO userDB_read, userDB_readwrite, userDB_admin;

-- READ
GRANT USAGE ON SCHEMA public TO userDB_read;
GRANT SELECT ON ALL TABLES TO userDB_read;

-- READWRITE
GRANT USAGE, CREATE ON SCHEMA public TO userDB_readwrite;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES TO userDB_readwrite;

-- ADMIN
GRANT ALL PRIVILEGES ON DATABASE userDB TO userDB_admin;
GRANT ALL PRIVILEGES ON SCHEMA public TO userDB_admin;
GRANT ALL PRIVILEGES ON ALL TABLES TO userDB_admin;

-- Future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT SELECT ON TABLES TO userDB_read;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT SELECT, INSERT, UPDATE ON TABLES TO userDB_readwrite;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT ALL ON TABLES TO userDB_admin;

-- Read
GRANT userDB_read TO jusong, reggie, josip, tobias;

-- Read/Write, script cannot delete important
GRANT userDB_readwrite TO script;

-- Admin
GRANT userDB_admin TO michal, vincent, ritwik, ping;