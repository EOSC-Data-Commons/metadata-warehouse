"""remove dependent endpoints (every endpoint is self-contained) and activate Zenodo

Revision ID: 0007_remove_dependencies
Revises: 0006_add_cern
Create Date: 2026-11-17 10:00:00

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0007_remove_dependencies'
down_revision: Union[str, Sequence[str], None] = '0006_add_cern'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove the dependency configuration from endpoints."""

    # Constraints first (dropping the columns would drop them as well, but this keeps the migration explicit)
    op.execute('ALTER TABLE endpoints DROP CONSTRAINT endpoints_dependency_config_consistent')
    op.execute('ALTER TABLE endpoints DROP CONSTRAINT endpoints_no_self_dependency')
    op.execute('ALTER TABLE endpoints DROP CONSTRAINT endpoints_depends_on_endpoint_id_fkey')

    # The column comments are dropped with the columns
    op.drop_column('endpoints', 'dependency_static_dois')
    op.drop_column('endpoints', 'dependency_match_pattern')
    op.drop_column('endpoints', 'dependency_xpath')
    op.drop_column('endpoints', 'depends_on_endpoint_id')

    # Zenodo is self-contained now, so it can be harvested like every other endpoint.
    # Idempotent: a no-op if Zenodo is already active (or does not exist), and updated_at is only touched on change.
    op.execute("UPDATE endpoints SET is_active = true WHERE name = 'Zenodo' AND is_active = false")


def downgrade() -> None:
    """Restore the dependency configuration of endpoints (the data of the dropped columns is not restored)."""

    # Without its dependency configuration Zenodo can no longer be harvested, so it is deactivated again (as in the seed)
    op.execute("UPDATE endpoints SET is_active = false WHERE name = 'Zenodo' AND is_active = true")

    op.execute('ALTER TABLE endpoints ADD COLUMN depends_on_endpoint_id UUID')
    op.execute('ALTER TABLE endpoints ADD COLUMN dependency_xpath TEXT')
    op.execute('ALTER TABLE endpoints ADD COLUMN dependency_match_pattern VARCHAR(255)')
    op.execute('ALTER TABLE endpoints ADD COLUMN dependency_static_dois TEXT[]')

    op.execute(
        """
        ALTER TABLE endpoints
        ADD CONSTRAINT endpoints_depends_on_endpoint_id_fkey FOREIGN KEY (depends_on_endpoint_id)
            REFERENCES endpoints(id) ON DELETE RESTRICT
        """
    )
    op.execute(
        """
        ALTER TABLE endpoints
        ADD CONSTRAINT endpoints_no_self_dependency
            CHECK (depends_on_endpoint_id IS DISTINCT FROM id)
        """
    )
    op.execute(
        """
        ALTER TABLE endpoints
        ADD CONSTRAINT endpoints_dependency_config_consistent
            CHECK (
                (depends_on_endpoint_id IS NULL AND dependency_xpath IS NULL AND dependency_match_pattern IS NULL)
                OR (depends_on_endpoint_id IS NOT NULL AND dependency_xpath IS NOT NULL AND dependency_match_pattern IS NOT NULL)
            )
        """
    )

    op.execute(
        "COMMENT ON COLUMN endpoints.depends_on_endpoint_id IS 'Optional master-set endpoint this endpoint depends on (e.g. Zenodo depends on HAL). Deleting a master endpoint is blocked (ON DELETE RESTRICT) while any dependent still references it.'"
    )
    op.execute(
        "COMMENT ON COLUMN endpoints.dependency_xpath IS 'XPath expression used to extract candidate identifier text nodes from the master endpoint''s raw_metadata (schema-specific, e.g. differs for datacite vs. other formats)'"
    )
    op.execute(
        "COMMENT ON COLUMN endpoints.dependency_match_pattern IS 'ILIKE pattern applied to the values extracted via dependency_xpath, to keep only identifiers relevant to this endpoint (e.g. %zenodo%)'"
    )
    op.execute(
        "COMMENT ON COLUMN endpoints.dependency_static_dois IS 'Optional fixed list of DOIs to always include in this endpoint''s master set, in addition to the dynamically derived ones'"
    )
