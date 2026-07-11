"""users.identity_user_id — link to the shared nousergon-auth identity service.

Revision ID: b8c9d0e1f2a3
Revises: a2b3c4d5e6f7
Create Date: 2026-07-11

Shared-identity cutover, phase 1 (vires-ops#60): adds the column mapping a
local ``User`` to nousergon-auth's stable ``user.id`` (the JWT ``sub``
claim). Purely additive — the legacy magic-link/session/allowlist tables are
retired only in a later migration, after the JWT path is verified live.

Nullable (existing rows predate the shared service; the dev user never gets
one) but unique when present, mirroring ``users.email``.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, Sequence[str], None] = "a2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("identity_user_id", sa.String(), nullable=True))
    op.create_index("ix_users_identity_user_id", "users", ["identity_user_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_identity_user_id", table_name="users")
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("identity_user_id")
