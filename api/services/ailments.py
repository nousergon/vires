"""Ailment episode helpers — pending check-ins, latest severity, coach context,
same-day prescription gate (shared by every workout-start path — vires-ops#58:
this used to live only in api.routers.plan, so ad-hoc/template starts via
api.routers.workouts never got gated)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from api.db.identity import Identity
from api.db.models import AilmentCheckIn, AilmentEpisode, Exercise
from api.services.coach.ailment_gate import AilmentFlag, ExerciseGateInput, gate_exercise

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


def open_ailment_flags(db: Session, ident: Identity) -> list[AilmentFlag]:
    """Latest severity of every open ailment episode, for the same-day
    prescription gate (see api.services.coach.ailment_gate). Episodes with no
    check-in yet (severity unknown) are excluded — the gate only reacts to a
    reported severity."""
    flags: list[AilmentFlag] = []
    for ep in load_open_ailments(db, ident):
        latest = latest_check_in(ep)
        if latest is not None:
            flags.append(AilmentFlag(label=ep.label, severity=latest.severity))
    return flags


def exercise_notes_with_gate(
    exercise_id: int, exercise: Exercise, notes: str | None, flags: list[AilmentFlag]
) -> str | None:
    """``notes`` with a lower-body/knee ailment warning prepended when the gate
    flags this exercise (see api.services.coach.ailment_gate)."""
    muscles = frozenset((exercise.primary_muscles or []) + (exercise.secondary_muscles or []))
    warning = gate_exercise(ExerciseGateInput(exercise_id=exercise_id, muscles=muscles), flags)
    if warning is None:
        return notes
    return f"{warning}\n{notes}" if notes else warning
