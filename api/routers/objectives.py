"""Objectives: the goals the coach periodizes toward.

CRUD over ``Objective`` plus ``/objectives/active`` (the derived *focus*
objective + the dated timeline + active constraints the coach generates
against). A user may hold several objectives at once; the focus is derived in
``api.services.objective_focus`` (next peak / ``is_primary`` override / standing
goal). ``is_primary`` is an optional manual override pin — at most one per user,
upheld here in the write path on top of the partial unique index.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from api.db.identity import Identity, current_identity
from api.db.models import Constraint, Objective, Program
from api.db.session import get_db
from api.schemas.objective import (
    ActiveObjectiveOut,
    ConstraintOut,
    ObjectiveCreate,
    ObjectiveOut,
    ObjectiveUpdate,
    ProgramStrategy,
)
from api.serializers import program_coach_summary
from api.services.coach.objective_profiles import demands_profile_for_sport
from api.services.objective_focus import (
    dated_timeline,
    load_objectives,
    pick_focus,
)

router = APIRouter(prefix="/objectives", tags=["objectives"])


def _get_owned(db: Session, objective_id: int, ident: Identity) -> Objective:
    o = db.get(Objective, objective_id)
    if o is None or o.tenant_id != ident.tenant_id or o.user_id != ident.user_id:
        raise HTTPException(404, "Objective not found")
    return o


def _demote_other_primaries(db: Session, ident: Identity, keep_id: int | None) -> None:
    """Clear is_primary on every objective for this user except ``keep_id`` —
    upholds the one-primary invariant before a row is set/inserted primary."""
    stmt = (
        update(Objective)
        .where(
            Objective.tenant_id == ident.tenant_id,
            Objective.user_id == ident.user_id,
            Objective.is_primary.is_(True),
        )
        .values(is_primary=False)
    )
    if keep_id is not None:
        stmt = stmt.where(Objective.id != keep_id)
    db.execute(stmt)


@router.get("", response_model=list[ObjectiveOut])
def list_objectives(
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> list[Objective]:
    return list(
        db.scalars(
            select(Objective)
            .where(
                Objective.tenant_id == ident.tenant_id,
                Objective.user_id == ident.user_id,
            )
            .order_by(
                Objective.is_primary.desc(),
                Objective.priority.desc(),
                Objective.created_at.desc(),
            )
        ).all()
    )


@router.get("/active", response_model=ActiveObjectiveOut)
def active_objective(
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> ActiveObjectiveOut:
    """The derived focus objective (if any) + the dated timeline + active
    constraints — the context objective-driven generation runs against. Drives
    the coach + the UI banner."""
    objectives = load_objectives(db, ident)
    primary = pick_focus(objectives, date.today())
    # Dated peaks chronologically, then any open-ended standing goals.
    timeline = dated_timeline(objectives)
    timeline_ids = {o.id for o in timeline}
    standing = sorted(
        (o for o in objectives if o.id not in timeline_ids),
        key=lambda o: (-(o.priority or 0), -(o.id or 0)),
    )
    ordered = timeline + standing
    constraints = db.scalars(
        select(Constraint)
        .where(
            Constraint.tenant_id == ident.tenant_id,
            Constraint.user_id == ident.user_id,
            Constraint.is_active.is_(True),
        )
        .order_by(Constraint.created_at)
    ).all()

    # The active plan generated for this objective, with the coach's strategy.
    strategy: ProgramStrategy | None = None
    if primary is not None:
        program = db.scalar(
            select(Program)
            .where(
                Program.tenant_id == ident.tenant_id,
                Program.user_id == ident.user_id,
                Program.objective_id == primary.id,
                Program.status == "active",
            )
            .order_by(Program.created_at.desc())
        )
        if program is not None:
            strategy = ProgramStrategy(
                program_id=program.id,
                name=program.name,
                coach_summary=program_coach_summary(program),
            )

    return ActiveObjectiveOut(
        objective=ObjectiveOut.model_validate(primary) if primary else None,
        objectives=[ObjectiveOut.model_validate(o) for o in ordered],
        constraints=[ConstraintOut.model_validate(c) for c in constraints],
        active_program=strategy,
    )


@router.get("/{objective_id}", response_model=ObjectiveOut)
def get_objective(
    objective_id: int,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> Objective:
    return _get_owned(db, objective_id, ident)


@router.post("", response_model=ObjectiveOut, status_code=201)
def create_objective(
    body: ObjectiveCreate,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> Objective:
    # Auto-fill the authored needs-analysis for the sport when not supplied.
    demands = body.demands_profile or demands_profile_for_sport(body.sport)
    if body.is_primary:
        _demote_other_primaries(db, ident, keep_id=None)
        db.flush()
    o = Objective(
        tenant_id=ident.tenant_id,
        user_id=ident.user_id,
        name=body.name.strip(),
        kind=body.kind,
        target_date=body.target_date,
        sport=body.sport,
        demands_profile=demands,
        is_primary=body.is_primary,
        priority=body.priority,
    )
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


@router.patch("/{objective_id}", response_model=ObjectiveOut)
def update_objective(
    objective_id: int,
    body: ObjectiveUpdate,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> Objective:
    o = _get_owned(db, objective_id, ident)
    data = body.model_dump(exclude_unset=True)

    if "name" in data and data["name"] is not None:
        o.name = data["name"].strip()
    if "kind" in data and data["kind"] is not None:
        o.kind = data["kind"]
    if "target_date" in data:
        o.target_date = data["target_date"]
    if "sport" in data:
        o.sport = data["sport"]
        # Refresh the authored profile to match the new sport unless one is
        # explicitly supplied in the same request.
        if "demands_profile" not in data:
            o.demands_profile = demands_profile_for_sport(o.sport)
    if "demands_profile" in data:
        o.demands_profile = data["demands_profile"]
    if "priority" in data and data["priority"] is not None:
        o.priority = data["priority"]

    # Validate the merged row: a dated objective must have a target_date.
    if o.kind == "dated" and o.target_date is None:
        raise HTTPException(400, "target_date is required when kind='dated'")

    if "is_primary" in data and data["is_primary"] is not None:
        if data["is_primary"]:
            _demote_other_primaries(db, ident, keep_id=o.id)
            db.flush()
            o.is_primary = True
        else:
            o.is_primary = False

    db.commit()
    db.refresh(o)
    return o


@router.delete("/{objective_id}", status_code=204)
def delete_objective(
    objective_id: int,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> Response:
    db.delete(_get_owned(db, objective_id, ident))
    db.commit()
    return Response(status_code=204)
