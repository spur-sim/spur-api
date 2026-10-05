"""add name to simulation_runs

Revision ID: c41d7a9e2b63
Revises: 01be612f1e22
Create Date: 2026-10-05 18:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c41d7a9e2b63'
down_revision: Union[str, None] = '01be612f1e22'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('simulation_runs', sa.Column('name', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('simulation_runs', 'name')
