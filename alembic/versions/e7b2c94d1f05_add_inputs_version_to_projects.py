"""add inputs_version to projects

Revision ID: e7b2c94d1f05
Revises: d5e8f1a3c720
Create Date: 2026-10-05 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e7b2c94d1f05'
down_revision: Union[str, None] = 'd5e8f1a3c720'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'projects',
        sa.Column('inputs_version', sa.Integer(), nullable=False, server_default='1'),
    )
    # Which earlier save last changed the inputs is not known, so take it to
    # be the latest: runs made before it are treated as out of date.
    op.execute('UPDATE projects SET inputs_version = version')


def downgrade() -> None:
    op.drop_column('projects', 'inputs_version')
