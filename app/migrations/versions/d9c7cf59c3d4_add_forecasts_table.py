"""Add forecasts table

Revision ID: d9c7cf59c3d4
Revises: 8400b2312556
Create Date: 2026-03-12 21:15:18.179415

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd9c7cf59c3d4'
down_revision: Union[str, Sequence[str], None] = '8400b2312556'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('forecasts',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('location_id', sa.UUID(), nullable=False),
    sa.Column('source_api', sa.String(length=50), nullable=False),
    sa.Column('start_time', sa.DateTime(timezone=True), nullable=False),
    sa.Column('end_time', sa.DateTime(timezone=True), nullable=False),
    sa.Column('temperature', sa.Float(), nullable=True),
    sa.Column('temperature_fahrenheit', sa.Float(), nullable=True),
    sa.Column('temp_low', sa.Float(), nullable=True),
    sa.Column('temp_low_fahrenheit', sa.Float(), nullable=True),
    sa.Column('feels_like', sa.Float(), nullable=True),
    sa.Column('humidity', sa.Integer(), nullable=True),
    sa.Column('pressure', sa.Float(), nullable=True),
    sa.Column('wind_speed', sa.Float(), nullable=True),
    sa.Column('wind_direction', sa.Integer(), nullable=True),
    sa.Column('wind_gust', sa.Float(), nullable=True),
    sa.Column('precipitation_probability', sa.Integer(), nullable=True),
    sa.Column('precipitation_amount', sa.Float(), nullable=True),
    sa.Column('cloud_cover', sa.Integer(), nullable=True),
    sa.Column('visibility', sa.Integer(), nullable=True),
    sa.Column('uv_index', sa.Float(), nullable=True),
    sa.Column('condition_text', sa.String(length=255), nullable=True),
    sa.Column('condition_code', sa.String(length=50), nullable=True),
    sa.Column('is_daytime', sa.Boolean(), nullable=True),
    sa.Column('detailed_forecast', sa.Text(), nullable=True),
    sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['location_id'], ['locations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id')
    )
    op.create_index('ix_forecasts_dedup', 'forecasts', ['location_id', 'source_api', 'start_time'], unique=True)
    op.create_index(op.f('ix_forecasts_location_id'), 'forecasts', ['location_id'], unique=False)
    op.create_index('ix_forecasts_location_time', 'forecasts', ['location_id', 'start_time'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_forecasts_location_time', table_name='forecasts')
    op.drop_index(op.f('ix_forecasts_location_id'), table_name='forecasts')
    op.drop_index('ix_forecasts_dedup', table_name='forecasts')
    op.drop_table('forecasts')
