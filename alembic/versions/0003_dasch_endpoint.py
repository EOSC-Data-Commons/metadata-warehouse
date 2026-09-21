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

    # No rows contain the dropped type, it's only part of the harvest_params additional metadata.
    # So we don't need to clean the values first.

    # We need to recreate the ENUM as a new object with a different name, then swap it instead of the upgraded version (containing the extra DASCH_API)
    # Then drop the original and change the enum name to the old name.
    # If we didn't do that, we'd lose the column data when changing type!
    op.execute("""
            CREATE TYPE harvest_protocol_new AS ENUM ('OAI-PMH', 'REST_API', 'FINBIF_API', 'MDPOSIT_API', 'EMPIAR_API', 'NFDI4EARTH_API');
            
            ALTER TABLE endpoints 
                ALTER COLUMN harvest_protocol TYPE harvest_protocol_new 
                USING harvest_protocol::text::harvest_protocol_new;
            
            DROP TYPE harvest_protocol;
            ALTER TYPE harvest_protocol_new RENAME TO harvest_protocol;
            """)
    
    # Now, update the endpoints table so that DaSCh has its initial harvest_params
    op.execute("""
            UPDATE endpoints
            SET harvest_params = '{"metadata_prefix": "oai_datacite","set": ["entityType:ResearchProject"]}'
            WHERE name = 'DaSCH';
            """)
