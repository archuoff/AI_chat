"""Engismart tables: user access (allowed domains), usage, upload decisions, pictures.

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tbl_engismart_user_access",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("domains", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "tbl_engismart_usage",
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tbl_engismart_usage_created_at", "tbl_engismart_usage", ["created_at"])
    op.create_index("ix_tbl_engismart_usage_user_id", "tbl_engismart_usage", ["user_id"])
    op.create_table(
        "tbl_engismart_upload_decision",
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tbl_engismart_upload_decision_created_at", "tbl_engismart_upload_decision", ["created_at"])
    op.create_index("ix_tbl_engismart_upload_decision_user_id", "tbl_engismart_upload_decision", ["user_id"])
    op.create_table(
        "tbl_engismart_image",
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
    op.create_index("ix_tbl_engismart_image_doc_id", "tbl_engismart_image", ["doc_id"])
    op.create_index("ix_tbl_engismart_image_sha256", "tbl_engismart_image", ["sha256"])
    op.create_index("ix_tbl_engismart_image_status", "tbl_engismart_image", ["status"])


def downgrade() -> None:
    for table in ("tbl_engismart_image", "tbl_engismart_upload_decision", "tbl_engismart_usage", "tbl_engismart_user_access"):
        op.drop_table(table)
