"""add raw_activities and threat_activities

Revision ID: a0423e8b00e7
Revises: efa5915465af
Create Date: 2026-08-31 18:10:00.000000

"""
import sqlalchemy as sa

from alembic import op

revision = 'a0423e8b00e7'
down_revision = 'efa5915465af'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'raw_activities',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('raw_persona_id', sa.UUID(), nullable=False),
        sa.Column('platform', sa.String(length=255), nullable=False),
        sa.Column('source_record_id', sa.String(length=255), nullable=False),
        sa.Column('title', sa.String(length=512), nullable=True),
        sa.Column('text', sa.String(length=4000), nullable=False),
        sa.Column('source_category', sa.String(length=128), nullable=True),
        sa.Column('observed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ingested_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['raw_persona_id'], ['raw_personas.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_record_id'),
    )
    op.create_index(
        op.f('ix_raw_activities_raw_persona_id'), 'raw_activities', ['raw_persona_id']
    )
    op.create_index(
        op.f('ix_raw_activities_source_record_id'), 'raw_activities', ['source_record_id']
    )

    op.create_table(
        'threat_activities',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('raw_activity_id', sa.UUID(), nullable=False),
        sa.Column('actor_id', sa.UUID(), nullable=True),
        sa.Column('persona_username', sa.String(length=255), nullable=False),
        sa.Column('source_platform', sa.String(length=255), nullable=False),
        sa.Column('source_record_id', sa.String(length=255), nullable=False),
        sa.Column('title', sa.String(length=512), nullable=True),
        sa.Column('observed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('category', sa.String(length=64), nullable=False),
        sa.Column('classification_reason', sa.String(length=512), nullable=False),
        sa.Column('classification_method', sa.String(length=32), nullable=False),
        sa.Column('classification_confidence', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['raw_activity_id'], ['raw_activities.id']),
        sa.ForeignKeyConstraint(['actor_id'], ['actors.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('raw_activity_id', name='uq_threat_activity_raw_activity'),
    )
    op.create_index(
        op.f('ix_threat_activities_raw_activity_id'), 'threat_activities', ['raw_activity_id']
    )
    op.create_index(op.f('ix_threat_activities_actor_id'), 'threat_activities', ['actor_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_threat_activities_actor_id'), table_name='threat_activities')
    op.drop_index(op.f('ix_threat_activities_raw_activity_id'), table_name='threat_activities')
    op.drop_table('threat_activities')
    op.drop_index(op.f('ix_raw_activities_source_record_id'), table_name='raw_activities')
    op.drop_index(op.f('ix_raw_activities_raw_persona_id'), table_name='raw_activities')
    op.drop_table('raw_activities')
