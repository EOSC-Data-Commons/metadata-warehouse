"""support JSON metadata in harvest events and records, check the dates of harvest runs

Revision ID: 0008_json_metadata
Revises: 0007_remove_dependencies
Create Date: 2026-11-17 12:00:00

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0008_json_metadata'
down_revision: Union[str, Sequence[str], None] = '0007_remove_dependencies'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ('harvest_events', 'records')


def upgrade() -> None:
    """Add raw_metadata_json (JSONB) next to raw_metadata (XML). Exactly one of them is set, depending on metadata_format."""

    for table in TABLES:
        op.execute(f'ALTER TABLE {table} ALTER COLUMN raw_metadata DROP NOT NULL')
        op.execute(f'ALTER TABLE {table} ADD COLUMN raw_metadata_json JSONB')
        op.execute(
            f"""
            ALTER TABLE {table}
            ADD CONSTRAINT {table}_raw_metadata_format_check
                CHECK (
                    (metadata_format = 'XML' AND raw_metadata IS NOT NULL AND raw_metadata_json IS NULL)
                    OR (metadata_format = 'JSON' AND raw_metadata_json IS NOT NULL AND raw_metadata IS NULL)
                )
            """
        )
        op.execute(f"COMMENT ON COLUMN {table}.raw_metadata IS 'Original harvested metadata, set if metadata_format is XML'")
        op.execute(
            f"COMMENT ON COLUMN {table}.raw_metadata_json IS 'Original harvested metadata, set if metadata_format is JSON (already normalized DataCite JSON)'"
        )

    # A harvest run must not end before it starts. from_date is derived in the same INSERT from the until_date of the
    # latest closed run, so this also guarantees that a new run is not older than the latest closed run.
    # Fails if existing runs violate this, find them with: SELECT * FROM harvest_runs WHERE from_date > until_date
    op.execute(
        """
        ALTER TABLE harvest_runs
        ADD CONSTRAINT harvest_runs_from_until_date_check
            CHECK (from_date IS NULL OR from_date <= until_date)
        """
    )


def downgrade() -> None:
    """Remove raw_metadata_json again. Fails if there are rows with JSON metadata, since they cannot be represented anymore."""

    op.execute('ALTER TABLE harvest_runs DROP CONSTRAINT harvest_runs_from_until_date_check')

    for table in TABLES:
        op.execute(
            f"""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM {table} WHERE raw_metadata IS NULL) THEN
                    RAISE EXCEPTION 'Cannot downgrade, table {table} contains rows with JSON metadata. Delete them first.';
                END IF;
            END
            $$
            """
        )
        op.execute(f'ALTER TABLE {table} DROP CONSTRAINT {table}_raw_metadata_format_check')
        op.execute(f'ALTER TABLE {table} DROP COLUMN raw_metadata_json')
        op.execute(f'ALTER TABLE {table} ALTER COLUMN raw_metadata SET NOT NULL')
        op.execute(f"COMMENT ON COLUMN {table}.raw_metadata IS 'Original harvested metadata (XML, JSON, etc.)'")
