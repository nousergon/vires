"""Ailment episode helpers — pending check-ins, latest severity, coach context."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from api.db.identity import Identity
from api.db.models import AilmentCheckIn, AilmentEpisode

_OPEN_STATUSES = ("active", "improving")


def load_open_ailments(db: Session, ident: Identity) -> list[AilmentEpisode]:
    return list(
        db.scalars(
            select(AilmentEpisode)
            .where(
                AilmentEpisode.tenant_id == ident.tenant_id,
                AilmentEpisode.user_id == ident.user_id,
                AilmentEpisode.status.in_(_OPEN_STATUSES),
            )
            .options(selectinload(AilmentEpisode.check_ins))
            .order_by(AilmentEpisode.onset_date.desc(), AilmentEpisode.id.desc())
        ).all()
    )


def latest_check_in(episode: AilmentEpisode) -> AilmentCheckIn | None:
    if not episode.check_ins:
        return None
    return max(episode.check_ins, key=lambda c: (c.check_in_date, c.id))


def pending_check_ins(
    db: Session, ident: Identity, on_date: date
) -> list[tuple[AilmentEpisode, AilmentCheckIn | None]]:
    """Open episodes with no check-in row for ``on_date``."""
    open_eps = load_open_ailments(db, ident)
    out: list[tuple[AilmentEpisode, AilmentCheckIn | None]] = []
    for ep in open_eps:
        has_today = any(c.check_in_date == on_date for c in ep.check_ins)
        if has_today:
            continue
        prior = latest_check_in(ep)
        out.append((ep, prior))
    return out
