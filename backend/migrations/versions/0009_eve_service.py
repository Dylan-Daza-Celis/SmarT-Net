"""Persist least-privilege EVE service accounts; existing users remain unchanged."""
from alembic import op
import sqlalchemy as sa

revision = '0009'
down_revision = '0008'


def upgrade():
    op.add_column('users', sa.Column('eve_only', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    raise RuntimeError('Destructive downgrade disabled; restore a verified backup')
