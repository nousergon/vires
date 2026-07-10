"""Auth: magic-link tokens, sessions, email allowlist, users.is_admin + unique email.

Revision ID: a2b3c4d5e6f7
Revises: e1f2a3b4c5d7
Create Date: 2026-07-10

Activates real multi-tenant auth (vires-ops#49): magic-link login backed by
a DB session (opaque token, hashed at rest — not a JWT, so it's revocable),
allowlist-gated signup. See ``api/routers/auth.py`` and ``api/db/identity.py``.

Signup is gated by ``allowed_emails`` (an admin pre-approves a specific
email, keyed by the address itself — not a shared secret code a user types
in) rather than an invite-code scheme: ``magic_link_tokens`` needs no
reference to it at all, since verify-time just looks up
``allowed_emails`` by the token's own ``email`` column.

``users.email`` gets a unique index (NULLs still allowed/distinct — the
existing dev user has none) rather than a NOT NULL constraint, since the
hardcoded dev row predates real accounts.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, Sequence[str], None] = "e1f2a3b4c5d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false())
        )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

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


def downgrade() -> None:
    op.drop_index("ix_user_sessions_tenant_id", table_name="user_sessions")
    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_table("user_sessions")

    op.drop_index("ix_magic_link_tokens_token_hash", table_name="magic_link_tokens")
    op.drop_index("ix_magic_link_tokens_email", table_name="magic_link_tokens")
    op.drop_table("magic_link_tokens")

    op.drop_table("allowed_emails")

    op.drop_index("ix_users_email", table_name="users")
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("is_admin")
