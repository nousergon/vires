"""Recording plan-change audit events.

A single seam both adaptation loops call so every automatic mutation of the
plan leaves an explainable row. Does NOT commit — the caller owns the
transaction so the audit row lands atomically with the change it describes.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from api.db.identity import Identity
from api.db.models import PlanChangeEvent


def record_plan_change(
    db: Session,
    ident: Identity,
    *,
    source: str,  # 'autoregulation' | 'plan_revision'
    summary: str,
    program_id: int | None = None,
    session_id: int | None = None,
    trigger: str | None = None,
    detail: dict[str, Any] | None = None,
) -> PlanChangeEvent:
    event = PlanChangeEvent(
        tenant_id=ident.tenant_id,
        user_id=ident.user_id,
        program_id=program_id,
        session_id=session_id,
        source=source,
        trigger=trigger,
        summary=summary,
        detail=detail,
    )
    db.add(event)
    return event
