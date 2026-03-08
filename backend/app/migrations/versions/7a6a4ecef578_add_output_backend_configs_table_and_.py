"""Add output_backend_configs table and locations slug column

Revision ID: 7a6a4ecef578
Revises: 82328944302f
Create Date: 2026-02-07 15:32:59.298804

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7a6a4ecef578'
down_revision: Union[str, Sequence[str], None] = '82328944302f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('output_backend_configs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('backend_type', sa.String(length=50), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('connection_config', sa.Text(), nullable=False),
    sa.Column('format_type', sa.String(length=50), nullable=True),
    sa.Column('format_config', sa.Text(), nullable=True),
    sa.Column('location_filter', sa.Text(), nullable=True),
    sa.Column('write_timeout', sa.Integer(), nullable=False),
    sa.Column('retry_count', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id')
    )
    op.create_index(op.f('ix_output_backend_configs_backend_type'), 'output_backend_configs', ['backend_type'], unique=False)
    op.add_column('locations', sa.Column('slug', sa.String(length=100), nullable=True))
    op.create_index(op.f('ix_locations_slug'), 'locations', ['slug'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_locations_slug'), table_name='locations')
    op.drop_column('locations', 'slug')
    op.drop_index(op.f('ix_output_backend_configs_backend_type'), table_name='output_backend_configs')
    op.drop_table('output_backend_configs')
