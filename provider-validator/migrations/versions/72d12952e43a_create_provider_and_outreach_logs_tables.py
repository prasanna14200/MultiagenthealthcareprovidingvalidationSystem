"""create provider and outreach logs tables

Revision ID: 72d12952e43a
Revises: 
Create Date: 2025-10-28 04:10:10.384755
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "72d12952e43a"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: create tables"""
    op.create_table(
        "providers",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("specialty", sa.String),
        sa.Column("address", sa.String),
        sa.Column("phone", sa.String),
        sa.Column("email", sa.String),
        sa.Column("confidence", sa.Float),
    )

    op.create_table(
        "outreach_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("provider_id", sa.Integer, sa.ForeignKey("providers.id")),
        sa.Column("subject", sa.String),
        sa.Column("body", sa.Text),
        sa.Column("recipient_email", sa.String),
        sa.Column("send_status", sa.String),
        sa.Column("send_time", sa.DateTime),
        sa.Column("provider_response_id", sa.String),
    )


def downgrade() -> None:
    """Downgrade schema: drop tables"""
    op.drop_table("outreach_logs")
    op.drop_table("providers")
