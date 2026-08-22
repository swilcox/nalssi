"""add radar_frames table

Revision ID: c310c1ab317c
Revises: d9c7cf59c3d4
Create Date: 2026-08-17 20:56:48.482170

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c310c1ab317c'
down_revision: Union[str, Sequence[str], None] = 'd9c7cf59c3d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # NOTE: autogenerate also reports NUMERIC -> UUID type changes on the
    # existing tables. Those are spurious (SQLite stores UUID columns as
    # NUMERIC) and have been removed by hand, as with previous migrations.
    op.create_table('radar_frames',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('location_id', sa.UUID(), nullable=False),
    sa.Column('frame_time', sa.DateTime(timezone=True), nullable=False),
    sa.Column('file_path', sa.String(length=512), nullable=False),
    sa.Column('file_size', sa.Integer(), nullable=False),
    sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['location_id'], ['locations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_radar_frames_dedup', 'radar_frames', ['location_id', 'frame_time'], unique=True)
    op.create_index(op.f('ix_radar_frames_location_id'), 'radar_frames', ['location_id'], unique=False)
    op.create_index('ix_radar_frames_location_time', 'radar_frames', ['location_id', 'frame_time'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_radar_frames_location_time', table_name='radar_frames')
    op.drop_index(op.f('ix_radar_frames_location_id'), table_name='radar_frames')
    op.drop_index('ix_radar_frames_dedup', table_name='radar_frames')
    op.drop_table('radar_frames')
