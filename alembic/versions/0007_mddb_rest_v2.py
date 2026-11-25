"""MDDB: switch harvest_url to REST API v2

Revision ID: 0007_mddb_rest_v2
Revises: 0006_add_cern
Create Date: 2026-11-24 12:00:00

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0007_mddb_rest_v2'
down_revision: Union[str, Sequence[str], None] = '0006_add_cern'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_URL = 'https://mdposit.mddbr.eu/api/rest/v1'
NEW_URL = 'https://mdposit.mddbr.eu/api/rest/v2'


def _set_harvest_url(old: str, new: str) -> None:
    op.execute(
        f"""
        UPDATE endpoints
        SET harvest_url = '{new}'
        WHERE harvest_url = '{old}'
          AND name = 'MDposit';
        """
    )


def upgrade() -> None:
    """Point the MDDB endpoint to the MDposit REST API v2."""
    _set_harvest_url(OLD_URL, NEW_URL)


def downgrade() -> None:
    """Point the MDDB endpoint back to the MDposit REST API v1."""
    _set_harvest_url(NEW_URL, OLD_URL)
