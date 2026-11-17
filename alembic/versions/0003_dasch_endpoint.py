"""dasch endpoint

Revision ID: 0003_dasch_endpoint
Revises: 0002_record_subjects
Create Date: 2026-09-21 09:31:00

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0003_dasch_endpoint'
down_revision: Union[str, Sequence[str], None] = '0002_record_subjects'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # Change the Enum to include DASCH_API
    op.execute("""
        ALTER TYPE harvest_protocol
        ADD VALUE 'DASCH_API';
        """)

    # Update harvest_params for DaSCH endpoint
    # The paramas are JSON that initially only has metadata_prefix and set
    op.execute("""
        UPDATE endpoints
        SET harvest_params = '{"metadata_prefix": "oai_datacite", "set": ["entityType:Record"], "additional_metadata_params": {"endpoint": "https://repository.dasch.swiss/dpe/records/", "protocol": "DASCH_API", "format": "None"}}'
        WHERE name = 'DaSCH';
        """)


def downgrade() -> None:
    """Downgrade schema."""

    # The downgrade includes changing the column type to restore the enum, so we have to drop and then re-create
    # all views that depend on the column.
    op.execute("""
        DROP VIEW v_active_harvest_endpoints;
    """)

    # No rows contain the dropped type, it's only part of the harvest_params additional metadata.
    # So we don't need to clean the values first.

    # We need to recreate the ENUM as a new object with a different name, then swap it instead of the upgraded version (containing the extra DASCH_API)
    # Then drop the original and change the enum name to the old name.
    # If we didn't do that, we'd lose the column data when changing type!
    # Also, we need to make it so endpoints.protocol doesn't have a default during the switch and then recreate it,
    # otherwise the ALTER will fail.

    # IMPORTANT: multiple columns use this enum! We need to alter each one. Only 'endpoints' has a default.
    op.execute("""
            CREATE TYPE harvest_protocol_new AS ENUM ('OAI-PMH', 'REST_API', 'FINBIF_API', 'MDPOSIT_API', 'EMPIAR_API', 'NFDI4EARTH_API');
            
            -- swap enum in all tables using it
            ALTER TABLE endpoints 
                ALTER COLUMN protocol DROP DEFAULT,
                ALTER COLUMN protocol TYPE harvest_protocol_new 
                    USING protocol::text::harvest_protocol_new;
            
            ALTER TABLE harvest_events 
            ALTER COLUMN metadata_protocol TYPE harvest_protocol_new 
                USING metadata_protocol::text::harvest_protocol_new;

            ALTER TABLE records 
            ALTER COLUMN metadata_protocol TYPE harvest_protocol_new 
                USING metadata_protocol::text::harvest_protocol_new;        

            -- drop enum, rename the newly created one to the same name    
            DROP TYPE harvest_protocol;
            ALTER TYPE harvest_protocol_new RENAME TO harvest_protocol;

            ALTER TABLE endpoints 
                ALTER COLUMN protocol SET DEFAULT 'OAI-PMH'::harvest_protocol;
            """)

    # Now, update the endpoints table so that DaSCh has its initial harvest_params
    op.execute("""
            UPDATE endpoints
            SET harvest_params = '{"metadata_prefix": "oai_datacite","set": ["entityType:ResearchProject"]}'
            WHERE name = 'DaSCH';
            """)

    # Re-create the view
    op.execute("""
        CREATE VIEW v_active_harvest_endpoints AS
            SELECT e.id AS endpoint_id,
                e.name AS endpoint_name,
                e.harvest_url,
                e.protocol,
                e.scientific_discipline,
                r.name AS repository_name,
                r.code AS repository_code,
                r.base_url AS repository_url
            FROM endpoints e
            JOIN repositories r ON e.repository_id = r.id
            WHERE e.is_active = true AND r.is_active = true;
    """)
