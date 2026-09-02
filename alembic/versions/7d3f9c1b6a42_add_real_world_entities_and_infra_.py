"""add real_world_entities, infra_finding severity/scan_job_id, correlation_evidence confidence

Revision ID: 7d3f9c1b6a42
Revises: c3f8a1d92e04
Create Date: 2026-09-02 09:00:00.000000

"""
import sqlalchemy as sa

from alembic import op

revision = '7d3f9c1b6a42'
down_revision = 'c3f8a1d92e04'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('infra_findings', sa.Column('severity', sa.String(length=16), nullable=True))
    op.add_column(
        'infra_findings', sa.Column('scan_job_id', sa.UUID(), nullable=True)
    )
    op.create_foreign_key(
        'fk_infra_findings_scan_job_id', 'infra_findings', 'analysis_jobs', ['scan_job_id'], ['id']
    )

    op.add_column(
        'correlation_evidence',
        sa.Column(
            'confidence', sa.String(length=32), nullable=False, server_default='exact_match'
        ),
    )
    op.alter_column('correlation_evidence', 'confidence', server_default=None)

    op.create_table(
        'real_world_entities',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('actor_id', sa.UUID(), nullable=False),
        sa.Column('entity_name', sa.String(length=512), nullable=False),
        sa.Column('entity_type', sa.String(length=32), nullable=False),
        sa.Column('relationship_type', sa.String(length=32), nullable=False),
        sa.Column('evidence', sa.JSON(), nullable=False),
        sa.Column('source', sa.String(length=64), nullable=False),
        sa.Column('source_record_id', sa.String(length=255), nullable=False),
        sa.Column('observed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('confidence', sa.String(length=64), nullable=False),
        sa.Column('explanation', sa.String(length=512), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['actor_id'], ['actors.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_real_world_entities_actor_id'), 'real_world_entities', ['actor_id']
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_real_world_entities_actor_id'), table_name='real_world_entities')
    op.drop_table('real_world_entities')
    op.drop_column('correlation_evidence', 'confidence')
    op.drop_constraint('fk_infra_findings_scan_job_id', 'infra_findings', type_='foreignkey')
    op.drop_column('infra_findings', 'scan_job_id')
    op.drop_column('infra_findings', 'severity')
