"""Add nullable speaker identity to transcript turns."""

import sqlalchemy as sa
from alembic import op

revision = "0002_panel_speaker_metadata"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing_columns = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("turns")
    }
    with op.batch_alter_table("turns") as batch_op:
        if "speaker_id" not in existing_columns:
            batch_op.add_column(sa.Column("speaker_id", sa.String(), nullable=True))
        if "speaker_name" not in existing_columns:
            batch_op.add_column(sa.Column("speaker_name", sa.String(), nullable=True))


def downgrade() -> None:
    existing_columns = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("turns")
    }
    with op.batch_alter_table("turns") as batch_op:
        if "speaker_name" in existing_columns:
            batch_op.drop_column("speaker_name")
        if "speaker_id" in existing_columns:
            batch_op.drop_column("speaker_id")
