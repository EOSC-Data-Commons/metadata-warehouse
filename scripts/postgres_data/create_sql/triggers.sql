
-- ============================================
-- 5. TRIGGERS
-- ============================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply update_updated_at trigger to tables
CREATE TRIGGER update_repositories_updated_at BEFORE UPDATE ON repositories
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_endpoints_updated_at BEFORE UPDATE ON endpoints
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_records_updated_at BEFORE UPDATE ON records
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Function to generate composite record ID
CREATE OR REPLACE FUNCTION generate_record_id()
RETURNS TRIGGER AS $$
BEGIN
    NEW.id = NEW.endpoint_id || '::' || NEW.record_identifier;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply generate_record_id trigger
CREATE TRIGGER generate_record_id_trigger BEFORE INSERT ON records
    FOR EACH ROW EXECUTE FUNCTION generate_record_id();
