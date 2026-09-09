-- Create the app user if it does not already exist
-- (roles are cluster-wide; this keeps tooldb setup independent of appdb ordering)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app') THEN
        CREATE USER app WITH PASSWORD 'app_password';
    END IF;
END
$$;

-- Grant read-only access on tooldb
GRANT CONNECT ON DATABASE tooldb TO app;
GRANT USAGE ON SCHEMA public TO app;

-- Grant SELECT on all existing and future tables
GRANT SELECT ON ALL TABLES IN SCHEMA public TO app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO app;
