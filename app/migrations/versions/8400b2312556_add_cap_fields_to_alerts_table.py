"""Add CAP fields to alerts table

Revision ID: 8400b2312556
Revises: 7a6a4ecef578
Create Date: 2026-03-11 21:36:50.934693

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8400b2312556'
down_revision: Union[str, Sequence[str], None] = '7a6a4ecef578'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('alerts', sa.Column('category', sa.String(length=50), nullable=True))
    op.add_column('alerts', sa.Column('response_type', sa.String(length=100), nullable=True))
    op.add_column('alerts', sa.Column('sender_name', sa.String(length=255), nullable=True))
    op.add_column('alerts', sa.Column('status', sa.String(length=50), nullable=True))
    op.add_column('alerts', sa.Column('message_type', sa.String(length=50), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('alerts', 'message_type')
    op.drop_column('alerts', 'status')
    op.drop_column('alerts', 'sender_name')
    op.drop_column('alerts', 'response_type')
    op.drop_column('alerts', 'category')
