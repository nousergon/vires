"""Drop legacy magic-link/session/allowlist auth tables.

Revision ID: d1e2f3a4b5c6
Revises: c9d0e1f2a3b4
Create Date: 2026-07-14

Shared-identity cutover, phase 2 (vires-ops#60) — DESTRUCTIVE. Drops
``magic_link_tokens``, ``user_sessions``, and ``allowed_emails``, the
backing tables for the legacy email magic-link login, cookie-based
sessions, and admin signup allowlist (vires-ops#49). Phase 1
(b8c9d0e1f2a3_identity_user_id) added the Bearer-JWT path against the
shared nousergon-auth service alongside the legacy path, non-destructively;
that JWT path has since been verified live in production (see
vires-ops#60's own comment thread, 2026-07-11 — a real login exercised end
to end with full history intact), so the legacy tables and the endpoints/
code that used them (``api.routers.auth``'s magic-link/session/allowlist
routes, ``api.db.identity``'s cookie-lookup branch) are retired for good in
this same change.

Irreversible by design: these tables held short-lived, security-sensitive
material (single-use magic-link tokens, session tokens hashed at rest) with
no durable value to restore — a downgrade recreates the empty table shape
(so a rollback of this migration leaves the schema consistent with the
pre-cutover ORM/routes if that code is also reverted) but intentionally
does NOT attempt to resurrect any rows: every one of them was either
already consumed/expired or would be stale and unusable by the time a
downgrade could run.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, Sequence[str], None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_magic_link_tokens_email", table_name="magic_link_tokens")
    op.drop_index("ix_magic_link_tokens_token_hash", table_name="magic_link_tokens")
    op.drop_table("magic_link_tokens")

    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_index("ix_user_sessions_tenant_id", table_name="user_sessions")
    op.drop_table("user_sessions")

    op.drop_table("allowed_emails")


def downgrade() -> None:
    """Schema-only reverse — recreates the table shapes but NOT their data.
    See the module docstring: this migration's data is deliberately not
    considered worth resurrecting (transient, security-sensitive tokens)."""
    op.create_table(
        "magic_link_tokens",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("request_ip", sa.String(), nullable=True),
    )
    op.create_index("ix_magic_link_tokens_email", "magic_link_tokens", ["email"])
    op.create_index(
        "ix_magic_link_tokens_token_hash", "magic_link_tokens", ["token_hash"], unique=True
    )

    op.create_table(
        "user_sessions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_index("ix_user_sessions_tenant_id", "user_sessions", ["tenant_id"])

    op.create_table(
        "allowed_emails",
        sa.Column("email", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.String(), nullable=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_by_user_id", sa.String(), nullable=True),
        sa.Column("note", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["used_by_user_id"], ["users.id"]),
    )
