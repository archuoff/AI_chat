"""Baseline: users, usage_events, upload_decisions, doc_images.

Databases created before migrations existed (tables made by create_all) already have some or all of these tables:
each table is only created when it is missing, so the first start of the new code adopts them without touching data.

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _existing() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    have = _existing()

    if "users" not in have:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("username", sa.String(length=64), nullable=False),
            sa.Column("display_name", sa.String(length=128), nullable=False),
            sa.Column("password_hash", sa.String(length=255), nullable=False),
            sa.Column("role", sa.String(length=16), nullable=False),
            sa.Column("domains", sa.JSON(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("token_version", sa.Integer(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_users_username", "users", ["username"], unique=True)

    if "usage_events" not in have:
        op.create_table(
            "usage_events",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("kind", sa.String(length=32), nullable=False),
            sa.Column("session_id", sa.String(length=128), nullable=False),
            sa.Column("question_chars", sa.Integer(), nullable=False),
            sa.Column("input_tokens", sa.Integer(), nullable=False),
            sa.Column("output_tokens", sa.Integer(), nullable=False),
            sa.Column("llm_calls", sa.Integer(), nullable=False),
            sa.Column("latency_ms", sa.Integer(), nullable=False),
            sa.Column("mode", sa.String(length=32), nullable=False),
            sa.Column("intent", sa.String(length=32), nullable=False),
            sa.Column("found", sa.Boolean(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_usage_events_created_at", "usage_events", ["created_at"])
        op.create_index("ix_usage_events_user_id", "usage_events", ["user_id"])

    if "upload_decisions" not in have:
        op.create_table(
            "upload_decisions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("check_id", sa.String(length=64), nullable=False),
            sa.Column("file_name", sa.String(length=255), nullable=False),
            sa.Column("domain", sa.String(length=64), nullable=False),
            sa.Column("intent", sa.String(length=16), nullable=False),
            sa.Column("replaces", sa.String(length=64), nullable=False),
            sa.Column("exact", sa.JSON(), nullable=False),
            sa.Column("suggestions", sa.JSON(), nullable=False),
            sa.Column("result_status", sa.String(length=16), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_upload_decisions_created_at", "upload_decisions", ["created_at"])
        op.create_index("ix_upload_decisions_user_id", "upload_decisions", ["user_id"])

    if "doc_images" not in have:
        op.create_table(
            "doc_images",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("doc_id", sa.String(length=64), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.Column("sha256", sa.String(length=64), nullable=False),
            sa.Column("location", sa.JSON(), nullable=False),
            sa.Column("context", sa.Text(), nullable=False),
            sa.Column("width", sa.Integer(), nullable=False),
            sa.Column("height", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("reason", sa.String(length=160), nullable=False),
            sa.Column("manual", sa.Boolean(), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("input_tokens", sa.Integer(), nullable=False),
            sa.Column("output_tokens", sa.Integer(), nullable=False),
            sa.Column("described_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_doc_images_doc_id", "doc_images", ["doc_id"])
        op.create_index("ix_doc_images_sha256", "doc_images", ["sha256"])
        op.create_index("ix_doc_images_status", "doc_images", ["status"])


def downgrade() -> None:
    for table in ("doc_images", "upload_decisions", "usage_events", "users"):
        op.drop_table(table)
