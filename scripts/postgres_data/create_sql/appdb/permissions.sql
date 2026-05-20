-- Create the app user if it does not already exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app') THEN
        CREATE USER app WITH PASSWORD 'raw_password';
    END IF;
END
$$;

-- Update password:
-- ALTER USER app WITH PASSWORD 'newpassword';

-- By default PostgreSQL grants CONNECT on every db to PUBLIC,
-- so any role (including app) can connect to any db unless we revoke it
REVOKE CONNECT ON DATABASE datasetdb FROM PUBLIC;
REVOKE CONNECT ON DATABASE filedb FROM PUBLIC;
REVOKE CONNECT ON DATABASE tooldb FROM PUBLIC;

-- Grant connect and usage on appdb only
GRANT CONNECT ON DATABASE appdb TO app;
GRANT USAGE ON SCHEMA public TO app;

-- Grant read and write on all existing tables and sequences
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app;

-- Apply the same grants to future tables and sequences
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO app;
