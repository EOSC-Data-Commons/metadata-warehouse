-- Enum Types (create if not exists in this db)
CREATE TYPE file_identifier_type AS ENUM ('DOI', 'URL', 'URN', 'HANDLE', 'ARK');
CREATE TYPE identifier_granularity_level AS ENUM ('Dataset');
CREATE TYPE checksum_algorithm AS ENUM ('MD5', 'SHA1', 'SHA256');

COMMENT ON TYPE identifier_granularity_level IS 'Granularity level of a file identifier; extend as new levels are encountered';
