"""add version to projects and project_version to simulation_runs

Revision ID: d5e8f1a3c720
Revises: c41d7a9e2b63
Create Date: 2026-10-05 19:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd5e8f1a3c720'
down_revision: Union[str, None] = 'c41d7a9e2b63'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing projects start at version 1, like new ones.
    op.add_column(
        'projects',
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
    )
    # Left null for existing runs: which version they ran is not known.
    op.add_column(
        'simulation_runs', sa.Column('project_version', sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('simulation_runs', 'project_version')
    op.drop_column('projects', 'version')
