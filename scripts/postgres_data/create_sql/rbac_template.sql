-- =========================================
-- Database RBAC template for {{DB_NAME}}
-- =========================================

\c {{DB_NAME}}

-- -----------------------------------------
-- 1. CREATE ROLE GROUPS (NOLOGIN)
-- -----------------------------------------
CREATE ROLE {{DB_NAME}}_read NOLOGIN;
CREATE ROLE {{DB_NAME}}_readwrite NOLOGIN;
CREATE ROLE {{DB_NAME}}_admin NOLOGIN;

-- -----------------------------------------
-- 2. DATABASE-LEVEL SECURITY
-- -----------------------------------------

-- Nobody connects by default
REVOKE CONNECT ON DATABASE {{DB_NAME}} FROM PUBLIC;

-- Only role groups may connect
GRANT CONNECT ON DATABASE {{DB_NAME}}
  TO {{DB_NAME}}_read,
     {{DB_NAME}}_readwrite,
     {{DB_NAME}}_admin;

-- -----------------------------------------
-- 3. SCHEMA LOCKDOWN
-- -----------------------------------------

-- Remove dangerous defaults
REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

-- -----------------------------------------
-- 4. SCHEMA ACCESS BY ROLE
-- -----------------------------------------

-- Read-only: see objects, nothing else
GRANT USAGE ON SCHEMA public TO {{DB_NAME}}_read;

-- Read-write: create & modify objects
GRANT USAGE, CREATE ON SCHEMA public TO {{DB_NAME}}_readwrite;

-- Admin: full control
GRANT ALL ON SCHEMA public TO {{DB_NAME}}_admin;

-- -----------------------------------------
-- 5. EXISTING OBJECT PRIVILEGES
-- -----------------------------------------

-- Tables
GRANT SELECT ON ALL TABLES IN SCHEMA public TO {{DB_NAME}}_read;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO {{DB_NAME}}_readwrite;
GRANT ALL ON ALL TABLES IN SCHEMA public TO {{DB_NAME}}_admin;

-- Sequences 
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {{DB_NAME}}_readwrite;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO {{DB_NAME}}_admin;

-- Functions
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public
  TO {{DB_NAME}}_read, {{DB_NAME}}_readwrite;
GRANT ALL ON ALL FUNCTIONS IN SCHEMA public TO {{DB_NAME}}_admin;

-- -----------------------------------------
-- 6. DEFAULT PRIVILEGES (FUTURE OBJECTS)
-- -----------------------------------------

-- Tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT SELECT ON TABLES TO {{DB_NAME}}_read;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT SELECT, INSERT, UPDATE ON TABLES TO {{DB_NAME}}_readwrite;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT ALL ON TABLES TO {{DB_NAME}}_admin;

-- Sequences
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT USAGE, SELECT ON SEQUENCES TO {{DB_NAME}}_readwrite;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT ALL ON SEQUENCES TO {{DB_NAME}}_admin;

-- Functions
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT EXECUTE ON FUNCTIONS
  TO {{DB_NAME}}_read, {{DB_NAME}}_readwrite;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT ALL ON FUNCTIONS TO {{DB_NAME}}_admin;