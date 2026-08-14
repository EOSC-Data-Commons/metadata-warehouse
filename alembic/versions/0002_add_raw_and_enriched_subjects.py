"""add_raw_and_enriched_subjects

Revision ID: 0002_record_subjects
Revises:
Create Date: 2026-08-14 10:30:12.770935

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0002_record_subjects'
down_revision: Union[str, Sequence[str], None] = '0001_baseline'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.execute("""
        ---- create raw_subjects and enriched_subjects columns

        ALTER TABLE records ADD COLUMN raw_subjects text[] DEFAULT ARRAY[]::text[];
        ALTER TABLE records ADD COLUMN enriched_subjects text[] DEFAULT ARRAY[]::text[];

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
