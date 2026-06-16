"""add_raw_and_enriched_subjects

Revision ID: c79e2b247d36
Revises:
Create Date: 2026-06-16 13:47:12.770935

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c79e2b247d36'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.execute("""
        ---- create raw_subjects and enriched_subjects columns if not already present

        ALTER TABLE records ADD COLUMN IF NOT EXISTS raw_subjects text[] DEFAULT ARRAY[]::text[];
        ALTER TABLE records ADD COLUMN IF NOT EXISTS enriched_subjects text[] DEFAULT ARRAY[]::text[];

        ---- fill raw_subjects based on datacite_json

        UPDATE records
        SET raw_subjects = ARRAY(
            SELECT jsonb_array_elements(datacite_json->'subjects')->>'subject'
        );
        """)


def downgrade() -> None:
    """Downgrade schema."""

    op.execute("""
        ALTER TABLE records
        DROP COLUMN raw_subjects;
        ALTER TABLE records
        DROP COLUMN enriched_subjects;
        """)
