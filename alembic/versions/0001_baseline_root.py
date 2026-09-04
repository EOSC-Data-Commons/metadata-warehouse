"""root

Revision ID: 0001_baseline
Revises:
Create Date: 2026-08-14 09:55:11.483473

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0001_baseline'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None # TODO: specify datasetdb?
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # This is the first database version created by `create_db.py`, no upgrade actions needed
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
