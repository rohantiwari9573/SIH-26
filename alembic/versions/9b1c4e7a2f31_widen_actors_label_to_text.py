"""widen actors.label to text

Revision ID: 9b1c4e7a2f31
Revises: 7d3f9c1b6a42
Create Date: 2026-09-09 00:00:00.000000

"""
import sqlalchemy as sa

from alembic import op

revision = '9b1c4e7a2f31'
down_revision = '7d3f9c1b6a42'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A cluster's label is every known alias joined with " / ", uncapped --
    # a real cluster can exceed 255 chars, which overflowed the old
    # VARCHAR(255) and crashed the whole re-attribution run (Actor rows are
    # rebuilt from scratch on every lead submission).
    op.alter_column('actors', 'label', existing_type=sa.String(length=255), type_=sa.Text())


def downgrade() -> None:
    op.alter_column('actors', 'label', existing_type=sa.Text(), type_=sa.String(length=255))
