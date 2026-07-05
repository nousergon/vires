"""Ailment episodes — date-anchored injuries with daily check-ins."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from api.db.identity import Identity, current_identity
from api.db.models import AilmentCheckIn, AilmentEpisode
from api.db.session import get_db
from api.schemas.ailment import (
    AilmentCheckInCreate,
    AilmentCheckInOut,
    AilmentEpisodeCreate,
    AilmentEpisodeOut,
    AilmentEpisodeUpdate,
    PendingAilmentCheckIn,
)
from api.services.ailments import latest_check_in, pending_check_ins

router = APIRouter(prefix="/ailments", tags=["ailments"])

_OPEN = ("active", "improving")


def _get_owned(db: Session, ailment_id: int, ident: Identity) -> AilmentEpisode:
    ep = db.scalar(
        select(AilmentEpisode)
        .where(
            AilmentEpisode.id == ailment_id,
            AilmentEpisode.tenant_id == ident.tenant_id,
            AilmentEpisode.user_id == ident.user_id,
        )
        .options(selectinload(AilmentEpisode.check_ins))
    )
    if ep is None:
        raise HTTPException(404, "Ailment not found")
    return ep


def _episode_out(ep: AilmentEpisode, *, include_check_ins: bool = True) -> AilmentEpisodeOut:
    latest = latest_check_in(ep)
    check_ins = (
        sorted(ep.check_ins, key=lambda c: c.check_in_date, reverse=True)
        if include_check_ins
        else []
    )
    return AilmentEpisodeOut(
        id=ep.id,
        label=ep.label,
        onset_date=ep.onset_date,
        notes=ep.notes,
        status=ep.status,
        resolved_at=ep.resolved_at,
        created_at=ep.created_at,
        updated_at=ep.updated_at,
        latest_severity=latest.severity if latest else None,
        latest_check_in_date=latest.check_in_date if latest else None,
        check_ins=[AilmentCheckInOut.model_validate(c) for c in check_ins],
    )


@router.get("", response_model=list[AilmentEpisodeOut])
def list_ailments(
    status: str = Query("open", description="open | active | improving | resolved | all"),
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> list[AilmentEpisodeOut]:
    q = select(AilmentEpisode).where(
        AilmentEpisode.tenant_id == ident.tenant_id,
        AilmentEpisode.user_id == ident.user_id,
    )
    if status == "open":
        q = q.where(AilmentEpisode.status.in_(_OPEN))
    elif status != "all":
        q = q.where(AilmentEpisode.status == status)
    rows = db.scalars(
        q.options(selectinload(AilmentEpisode.check_ins)).order_by(
            AilmentEpisode.onset_date.desc(), AilmentEpisode.id.desc()
        )
    ).all()
    return [_episode_out(ep) for ep in rows]


@router.get("/pending-check-ins", response_model=list[PendingAilmentCheckIn])
def list_pending_check_ins(
    on_date: date | None = Query(None, alias="date"),
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> list[PendingAilmentCheckIn]:
    day = on_date or date.today()
    pending = pending_check_ins(db, ident, day)
    return [
        PendingAilmentCheckIn(
            ailment=_episode_out(ep, include_check_ins=False),
            last_severity=last.severity if last else None,
            last_check_in_date=last.check_in_date if last else None,
        )
        for ep, last in pending
    ]


@router.post("", response_model=AilmentEpisodeOut, status_code=201)
def create_ailment(
    body: AilmentEpisodeCreate,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> AilmentEpisodeOut:
    onset = body.onset_date or date.today()
    ep = AilmentEpisode(
        tenant_id=ident.tenant_id,
        user_id=ident.user_id,
        label=body.label.strip(),
        onset_date=onset,
        notes=body.notes,
        status="active",
    )
    db.add(ep)
    db.flush()
    if body.initial_severity is not None:
        db.add(
            AilmentCheckIn(
                ailment_id=ep.id,
                check_in_date=onset,
                severity=body.initial_severity,
                note=body.notes,
            )
        )
    db.commit()
    db.refresh(ep)
    ep = _get_owned(db, ep.id, ident)
    return _episode_out(ep)


@router.patch("/{ailment_id}", response_model=AilmentEpisodeOut)
def update_ailment(
    ailment_id: int,
    body: AilmentEpisodeUpdate,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> AilmentEpisodeOut:
    ep = _get_owned(db, ailment_id, ident)
    data = body.model_dump(exclude_unset=True)
    if "label" in data and data["label"] is not None:
        ep.label = data["label"].strip()
    if "notes" in data:
        ep.notes = data["notes"]
    if "status" in data and data["status"] is not None:
        ep.status = data["status"]
        if data["status"] == "resolved":
            ep.resolved_at = date.today()
        elif ep.resolved_at is not None:
            ep.resolved_at = None
    db.commit()
    ep = _get_owned(db, ailment_id, ident)
    return _episode_out(ep)


@router.post("/{ailment_id}/check-ins", response_model=AilmentCheckInOut, status_code=201)
def add_check_in(
    ailment_id: int,
    body: AilmentCheckInCreate,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> AilmentCheckIn:
    ep = _get_owned(db, ailment_id, ident)
    if ep.status == "resolved":
        raise HTTPException(400, "Cannot check in on a resolved ailment")
    day = body.check_in_date or date.today()
    existing = db.scalar(
        select(AilmentCheckIn).where(
            AilmentCheckIn.ailment_id == ep.id,
            AilmentCheckIn.check_in_date == day,
        )
    )
    if existing is not None:
        existing.severity = body.severity
        existing.note = body.note
        db.commit()
        db.refresh(existing)
        return existing
    row = AilmentCheckIn(
        ailment_id=ep.id,
        check_in_date=day,
        severity=body.severity,
        note=body.note,
    )
    db.add(row)
    if body.severity <= 2 and ep.status == "active":
        ep.status = "improving"
    elif body.severity >= 6:
        ep.status = "active"
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{ailment_id}", status_code=204)
def delete_ailment(
    ailment_id: int,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> None:
    ep = _get_owned(db, ailment_id, ident)
    db.delete(ep)
    db.commit()
