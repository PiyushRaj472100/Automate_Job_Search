"""add_source_to_search_runs

Revision ID: 5b91481b2b94
Revises: 708e79ba2898
Create Date: 2026-09-28 06:33:43.970052

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5b91481b2b94'
down_revision: Union[str, Sequence[str], None] = '708e79ba2898'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('search_runs', sa.Column('source', sa.String(length=100), nullable=True))
    op.create_index(op.f('ix_search_runs_source'), 'search_runs', ['source'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_search_runs_source'), table_name='search_runs')
    op.drop_column('search_runs', 'source')
