"""add_raw_and_enriched_subjects

Revision ID: 0002_record_subjects
Revises: 0001_baseline
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

    # create raw_subjects and enriched_subjects columns
    op.add_column(
        "records",
        sa.Column(
            "raw_subjects",
            sa.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("ARRAY[]::text[]"),
        ),
    )
    op.add_column(
        "records",
        sa.Column(
            "enriched_subjects",
            sa.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("ARRAY[]::text[]"),
        ),
    )

    # fill raw_subjects based on datacite_json
    op.execute("""
        UPDATE records
        SET raw_subjects = ARRAY(
            SELECT jsonb_array_elements(datacite_json->'subjects')->>'subject'
        );
        """)



def downgrade() -> None:
    """Downgrade schema."""

    op.drop_column("records", "raw_subjects")
    op.drop_column("records", "enriched_subjects")
