"""dataverseua

Revision ID: 0004_add_dataverseua
Revises: 0003_dasch_endpoint
Create Date: 2026-10-02 12:35:00

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0004_add_dataverseua'
down_revision: Union[str, Sequence[str], None] = '0003_dasch_endpoint'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add DataverseUA repository and endpoint."""

    # Add repository
    op.execute(
        """
        INSERT INTO repositories (
            name,
            code,
            description,
            base_url,
            is_active
        )
        VALUES (
            'DataverseUA',
            'DATAVERSEUA',
            'Dataverse UA is a national research data repository designed to support open science and implement the FAIR principles in Ukraine',
            'https://opendata.nas.gov.ua/dataverse/dataverseua',
            true
        )
        ON CONFLICT (code) DO NOTHING;
        """
    )

    # Add endpoint
    op.execute(
        """
        INSERT INTO endpoints (
            repository_id,
            name,
            harvest_url,
            protocol,
            scientific_discipline,
            is_active,
            harvest_params,
            harvest_schedule
        )
        SELECT
            r.id,
            'DataverseUA',
            'https://opendata.nas.gov.ua/oai',
            'OAI-PMH',
            'Multidisciplinary',
            true,
            '{"metadata_prefix": "oai_datacite", "additional_metadata_params": {"endpoint": "https://opendata.nas.gov.ua/api/datasets/\:persistentId/versions/\:latest-published", "protocol": "DATAVERSE_API", "format": "None"}}',
            INTERVAL '1 week'
        FROM repositories r
        WHERE r.code = 'DATAVERSEUA'
        ON CONFLICT (name) DO NOTHING;
        """
    )


def downgrade() -> None:
    """Remove DataverseUA endpoint and repository."""

    # Delete endpoint first because it references the repository
    op.execute(
        """
        DELETE FROM endpoints
        WHERE name = 'DataverseUA';
        """
    )

    op.execute(
        """
        DELETE FROM repositories
        WHERE code = 'DATAVERSEUA';
        """
    )
