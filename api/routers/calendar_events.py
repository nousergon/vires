"""CalendarEvent: external athletic events the coach trains *around* (not
toward — see ``Objective`` for goals). CRUD plus ``/calendar-events/window``,
which expands ``recurrence='weekly'`` series into concrete occurrence dates
within a queried date range (server-side; never persisted — see
``api.services.calendar_events``).
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db.identity import Identity, current_identity
from api.db.models import CalendarEvent, Objective
from api.db.session import get_db
from api.schemas.calendar_event import (
    CalendarEventCreate,
    CalendarEventOccurrence,
    CalendarEventOut,
    CalendarEventUpdate,
)
from api.services.calendar_events import expand_occurrences

router = APIRouter(prefix="/calendar-events", tags=["calendar-events"])


def _get_owned(db: Session, event_id: int, ident: Identity) -> CalendarEvent:
    e = db.get(CalendarEvent, event_id)
    if e is None or e.tenant_id != ident.tenant_id or e.user_id != ident.user_id:
        raise HTTPException(404, "Calendar event not found")
    return e


def _load_dict(body: CalendarEventCreate | CalendarEventUpdate) -> dict | None:
    return body.load.model_dump() if body.load is not None else None


def _require_owned_objective(db: Session, ident: Identity, objective_id: int) -> None:
    o = db.get(Objective, objective_id)
    if o is None or o.tenant_id != ident.tenant_id or o.user_id != ident.user_id:
        raise HTTPException(404, "Objective not found")


@router.get("", response_model=list[CalendarEventOut])
def list_calendar_events(
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> list[CalendarEvent]:
    return list(
        db.scalars(
            select(CalendarEvent)
            .where(
                CalendarEvent.tenant_id == ident.tenant_id,
                CalendarEvent.user_id == ident.user_id,
            )
            .order_by(CalendarEvent.event_date)
        ).all()
    )


@router.get("/window", response_model=list[CalendarEventOccurrence])
def calendar_events_window(
    start: date = Query(...),
    end: date = Query(...),
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> list[CalendarEventOccurrence]:
    """Concrete occurrences of every event within ``[start, end]`` — the coach's
    lookahead window. A weekly recurring event expands to one occurrence per
    matching week; a one-off event yields at most one occurrence."""
    if end < start:
        raise HTTPException(400, "end must be on or after start")

    events = db.scalars(
        select(CalendarEvent).where(
            CalendarEvent.tenant_id == ident.tenant_id,
            CalendarEvent.user_id == ident.user_id,
        )
    ).all()

    occurrences: list[CalendarEventOccurrence] = []
    for e in events:
        for occ_date, occ_end_date in expand_occurrences(e, start, end):
            occurrences.append(
                CalendarEventOccurrence(
                    event=CalendarEventOut.model_validate(e),
                    occurrence_date=occ_date,
                    occurrence_end_date=occ_end_date,
                )
            )
    occurrences.sort(key=lambda o: (o.occurrence_date, o.event.id))
    return occurrences


@router.get("/{event_id}", response_model=CalendarEventOut)
def get_calendar_event(
    event_id: int,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> CalendarEvent:
    return _get_owned(db, event_id, ident)


@router.post("", response_model=CalendarEventOut, status_code=201)
def create_calendar_event(
    body: CalendarEventCreate,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> CalendarEvent:
    if body.objective_id is not None:
        _require_owned_objective(db, ident, body.objective_id)
    e = CalendarEvent(
        tenant_id=ident.tenant_id,
        user_id=ident.user_id,
        name=body.name.strip(),
        sport=body.sport,
        type=body.type,
        event_date=body.event_date,
        event_end_date=body.event_end_date,
        recurrence=body.recurrence,
        load=_load_dict(body),
        notes=body.notes,
        objective_id=body.objective_id,
    )
    db.add(e)
    db.commit()
    db.refresh(e)
    return e


@router.patch("/{event_id}", response_model=CalendarEventOut)
def update_calendar_event(
    event_id: int,
    body: CalendarEventUpdate,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> CalendarEvent:
    e = _get_owned(db, event_id, ident)
    data = body.model_dump(exclude_unset=True)

    if "name" in data and data["name"] is not None:
        e.name = data["name"].strip()
    if "sport" in data:
        e.sport = data["sport"]
    if "type" in data and data["type"] is not None:
        e.type = data["type"]
    if "event_date" in data and data["event_date"] is not None:
        e.event_date = data["event_date"]
    if "event_end_date" in data:
        e.event_end_date = data["event_end_date"]
    if "recurrence" in data and data["recurrence"] is not None:
        e.recurrence = data["recurrence"]
    if "load" in data:
        e.load = data["load"]
    if "notes" in data:
        e.notes = data["notes"]
    if "objective_id" in data:
        if data["objective_id"] is not None:
            _require_owned_objective(db, ident, data["objective_id"])
        e.objective_id = data["objective_id"]

    # Validate the merged row: a multi-day event must end on/after it starts.
    if e.event_end_date is not None and e.event_end_date < e.event_date:
        raise HTTPException(400, "event_end_date must be on or after event_date")

    db.commit()
    db.refresh(e)
    return e


@router.delete("/{event_id}", status_code=204)
def delete_calendar_event(
    event_id: int,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> Response:
    db.delete(_get_owned(db, event_id, ident))
    db.commit()
    return Response(status_code=204)
