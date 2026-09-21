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
    # The paramas are JSON that initially only has entityType:ResearchProject
    op.execute("""
        UPDATE endpoints
        SET harvest_params = '{"metadata_prefix": "oai_datacite", "set": ["entityType:Record"], "additional_metadata_params": {"endpoint": "https://repository.dasch.swiss/dpe/records/", "protocol": "DASCH_API", "format": "None"}}'
        WHERE name = 'DaSCH';
        """)



def downgrade() -> None:
    """Downgrade schema."""

    #TODO:
    # ALTER TYPE or recreate TYPE to only the informaton it used to have
    # UPDATE endpoints table for dasch to data it used to have

    op.drop_column('records', 'raw_subjects')
    op.drop_column('records', 'enriched_subjects')
