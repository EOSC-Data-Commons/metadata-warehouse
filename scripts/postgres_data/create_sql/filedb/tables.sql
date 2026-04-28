CREATE TABLE IF NOT EXISTS record_files (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    harvest_url VARCHAR(500) NOT NULL,
    record_identifier TEXT NOT NULL,
    file_identifier TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_information_method TEXT,
    identifier_type file_identifier_type NOT NULL,
    identifier_granularity identifier_granularity_level NOT NULL DEFAULT 'Dataset',
    file_type TEXT,
    file_size BIGINT,
    checksum_type checksum_algorithm,
    checksum_value VARCHAR(128),
    file_version VARCHAR(50),
    download_url VARCHAR(2048) NOT NULL,
    file_created_at TIMESTAMP WITH TIME ZONE,
    file_last_modified_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT record_files_pkey PRIMARY KEY (id),
    CONSTRAINT record_files_harvest_url_record_identifier_file_identifier_key
        UNIQUE (harvest_url, record_identifier, file_identifier),
    CONSTRAINT record_files_checksum_check CHECK (
        (checksum_type IS NULL AND checksum_value IS NULL) OR
        (checksum_type IS NOT NULL AND checksum_value IS NOT NULL)
    )
);

COMMENT ON TABLE record_files IS 'File-level metadata for files linked to harvested records';
COMMENT ON COLUMN record_files.id IS 'Synthetic UUID primary key';
COMMENT ON COLUMN record_files.harvest_url IS 'References endpoints.harvest_url - unique endpoint identifier';
COMMENT ON COLUMN record_files.record_identifier IS 'OAI-PMH identifier or unique record ID of the parent record';
COMMENT ON COLUMN record_files.file_identifier IS 'Source-assigned identifier for the file';
COMMENT ON COLUMN record_files.file_name IS 'Name of the file';
COMMENT ON COLUMN record_files.file_information_method IS 'Method used to get file information';
COMMENT ON COLUMN record_files.identifier_type IS 'Type of identifier for this file: DOI, URL, URN, etc.';
COMMENT ON COLUMN record_files.identifier_granularity IS 'Granularity level of the identifier (e.g., Dataset)';
COMMENT ON COLUMN record_files.file_type IS 'MIME type of the file (e.g., application/pdf)';
COMMENT ON COLUMN record_files.file_size IS 'File size in bytes';
COMMENT ON COLUMN record_files.checksum_type IS 'Algorithm used for checksum: MD5, SHA1, SHA256';
COMMENT ON COLUMN record_files.checksum_value IS 'Checksum hash value';
COMMENT ON COLUMN record_files.file_version IS 'Version indicator for the file';
COMMENT ON COLUMN record_files.download_url IS 'URL for downloading the file';
COMMENT ON COLUMN record_files.file_created_at IS 'Timestamp when the file was originally created at the source';
COMMENT ON COLUMN record_files.file_last_modified_at IS 'Timestamp when the file was last modified at the source';
