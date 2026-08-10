"""Initial production schema.

Revision ID: 20260810_0001
Revises:
"""

from alembic import op

from server.database import Base
from server import models  # noqa: F401


revision = "20260810_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
