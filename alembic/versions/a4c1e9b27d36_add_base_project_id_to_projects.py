"""add base_project_id to projects

Revision ID: a4c1e9b27d36
Revises: f3a9c0d47e18
Create Date: 2026-10-07 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a4c1e9b27d36'
down_revision: Union[str, None] = 'f3a9c0d47e18'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('projects', sa.Column('base_project_id', sa.UUID(), nullable=True))
    op.create_index(
        op.f('ix_projects_base_project_id'), 'projects', ['base_project_id']
    )
    op.create_foreign_key(
        op.f('fk_projects_base_project_id_projects'),
        'projects',
        'projects',
        ['base_project_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f('fk_projects_base_project_id_projects'), 'projects', type_='foreignkey'
    )
    op.drop_index(op.f('ix_projects_base_project_id'), table_name='projects')
    op.drop_column('projects', 'base_project_id')
