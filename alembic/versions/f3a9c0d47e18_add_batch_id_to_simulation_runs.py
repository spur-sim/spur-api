"""add batch_id to simulation_runs

Revision ID: f3a9c0d47e18
Revises: e7b2c94d1f05
Create Date: 2026-10-06 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f3a9c0d47e18'
down_revision: Union[str, None] = 'e7b2c94d1f05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('simulation_runs', sa.Column('batch_id', sa.UUID(), nullable=True))
    op.create_index(
        op.f('ix_simulation_runs_batch_id'), 'simulation_runs', ['batch_id']
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_simulation_runs_batch_id'), table_name='simulation_runs')
    op.drop_column('simulation_runs', 'batch_id')
