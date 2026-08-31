"""add task_id to analysis_jobs

Revision ID: c3f8a1d92e04
Revises: a0423e8b00e7
Create Date: 2026-09-01 01:15:00.000000

"""
import sqlalchemy as sa

from alembic import op

revision = 'c3f8a1d92e04'
down_revision = 'a0423e8b00e7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('analysis_jobs', sa.Column('task_id', sa.String(length=64), nullable=True))
    op.create_index(op.f('ix_analysis_jobs_task_id'), 'analysis_jobs', ['task_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_analysis_jobs_task_id'), table_name='analysis_jobs')
    op.drop_column('analysis_jobs', 'task_id')
