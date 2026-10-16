"""CERN

Revision ID: 0006_add_cern
Revises: 0005_remove_doi
Create Date: 2026-10-16 13:55:00

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0006_add_cern'
down_revision: Union[str, Sequence[str], None] = '0005_remove_doi'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add Cern repository and endpoint."""

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
            'CERN Open Data Portal',
            'CERN',
            'CERN Open Data is a public repository providing access to research data, software, and documentation from CERN's particle physics experiments.',
            'https://opendata.cern.ch/',
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
            'CERN Open Data Portal',
            'https://opendata.cern.ch/oai2d',
            'OAI-PMH',
            'Multidisciplinary',
            true,
            '{"metadata_prefix": "oai_datacite"}',
            INTERVAL '1 week'
        FROM repositories r
        WHERE r.code = 'CERN'
        ON CONFLICT (name) DO NOTHING;
        """
    )


def downgrade() -> None:
    """Remove CERN endpoint and repository."""

    # Delete endpoint first because it references the repository
    op.execute(
        """
        DELETE FROM endpoints
        WHERE name = 'CERN Open Data Portal';
        """
    )

    op.execute(
        """
        DELETE FROM repositories
        WHERE code = 'CERN';
        """
    )
