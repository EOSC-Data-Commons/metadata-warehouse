"""remove doi from records, make url mandatory

Revision ID: 0005_remove_doi
Revises: 0004_add_dataverseua
Create Date: 2026-10-07 15:10:00
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0005_remove_doi'
down_revision: Union[str, Sequence[str], None] = '0004_add_dataverseua'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DOI_URL_PREFIX = 'https://doi.org/'

VIEW_WITHOUT_DOI = """
CREATE VIEW v_records_statistics AS
SELECT
    r.name as repository_name,
    e.name as endpoint_name,
    rec.resource_type,
    COUNT(*) as record_count,
    COUNT(DISTINCT rec.url) as unique_urls,
    COUNT(CASE WHEN rec.opensearch_synced THEN 1 END) as synced_count,
    MAX(rec.updated_at) as last_updated
FROM records rec
JOIN endpoints e ON rec.endpoint_id = e.id
JOIN repositories r ON rec.repository_id = r.id
GROUP BY r.name, e.name, rec.resource_type
"""

VIEW_WITH_DOI = """
CREATE VIEW v_records_statistics AS
SELECT
    r.name as repository_name,
    e.name as endpoint_name,
    rec.resource_type,
    COUNT(*) as record_count,
    COUNT(DISTINCT rec.doi) as unique_dois,
    COUNT(CASE WHEN rec.opensearch_synced THEN 1 END) as synced_count,
    MAX(rec.updated_at) as last_updated
FROM records rec
JOIN endpoints e ON rec.endpoint_id = e.id
JOIN repositories r ON rec.repository_id = r.id
GROUP BY r.name, e.name, rec.resource_type
"""


def upgrade() -> None:
    # 1. The view depends on records.doi, so it must go first
    #    (CREATE OR REPLACE VIEW cannot remove a column).
    op.execute('DROP VIEW IF EXISTS v_records_statistics')

    # 2. Data: backfill url from doi where no url is set yet. An existing url
    #    is never overwritten. Values that already are a full URL are kept
    #    as-is to avoid double prefixes.
    op.execute(f"""
        UPDATE records
        SET url = CASE
                WHEN doi ~* '^https?://' THEN doi
                ELSE '{DOI_URL_PREFIX}' || doi
            END
        WHERE doi IS NOT NULL
          AND url IS NULL
    """)

    # 3. Constraint: (doi OR url) -> url NOT NULL
    #    All rows have a url at this point (old check + step 2).
    op.execute('ALTER TABLE records DROP CONSTRAINT IF EXISTS records_doi_or_url_check')
    op.alter_column('records', 'url', nullable=False)

    # 4. Drop doi index and column (the column comment is dropped with the column)
    op.execute('DROP INDEX IF EXISTS idx_records_doi')
    op.drop_column('records', 'doi')

    # 5. Index on url
    op.execute('CREATE INDEX IF NOT EXISTS idx_records_url ON records(url)')

    # 6. Recreate the view without doi
    op.execute(VIEW_WITHOUT_DOI)


def downgrade() -> None:
    op.execute('DROP VIEW IF EXISTS v_records_statistics')
    op.execute('DROP INDEX IF EXISTS idx_records_url')

    # Restore column + comment
    op.execute('ALTER TABLE records ADD COLUMN doi VARCHAR(255)')
    op.execute("COMMENT ON COLUMN records.doi IS 'Digital Object Identifier'")

    # Data: url -> doi for DOI URLs. url is cleared for those rows, matching the
    # old semantics ("Primary URL if no DOI"). Original url values of rows that
    # had both doi and url cannot be recovered.
    op.alter_column('records', 'url', nullable=True)
    # length('https://doi.org/') = 16, so the DOI starts at position 17
    op.execute(f"""
        UPDATE records
        SET doi = substr(url, {len(DOI_URL_PREFIX) + 1}),
            url = NULL
        WHERE url ILIKE '{DOI_URL_PREFIX}%'
    """)

    # Restore constraint and index
    op.execute("""
        ALTER TABLE records
        ADD CONSTRAINT records_doi_or_url_check CHECK (doi IS NOT NULL OR url IS NOT NULL)
    """)
    op.execute('CREATE INDEX IF NOT EXISTS idx_records_doi ON records(doi) WHERE doi IS NOT NULL')

    # Restore the original view
    op.execute(VIEW_WITH_DOI)
