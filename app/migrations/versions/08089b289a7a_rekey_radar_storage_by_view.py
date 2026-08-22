"""rekey radar storage by view

Radar files used to live under a per-location directory. They are now keyed by
the radar view (source + bounding box) so that locations sharing coordinates —
a common way to compare two weather providers for one place — share a single
set of downloads instead of duplicating them.

That makes every existing `file_path` stale. Radar frames are a rolling
two-hour cache that backfills in one collection cycle, so the rows are simply
cleared rather than migrated; the next cycle repopulates them under the new
layout and sweeps the old directories.

Revision ID: 08089b289a7a
Revises: c310c1ab317c
Create Date: 2026-08-18 16:05:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '08089b289a7a'
down_revision: Union[str, Sequence[str], None] = 'c310c1ab317c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Clear the radar frame cache so it repopulates under the new layout."""
    op.execute("DELETE FROM radar_frames")


def downgrade() -> None:
    """Clear it again: paths written by the new layout mean nothing to the old."""
    op.execute("DELETE FROM radar_frames")
