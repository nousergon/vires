"""Constraints: bounds the coach trains *around* (never goals).

CRUD over ``Constraint``. An injury constraint defaults ``defer_to_professional``
on (the coach never prescribes to treat it). Active constraints feed every
generation; deactivate (vs delete) to retain history.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db.identity import Identity, current_identity
from api.db.models import Constraint
from api.db.session import get_db
from api.schemas.objective import (
    ConstraintCreate,
    ConstraintOut,
    ConstraintUpdate,
)

router = APIRouter(prefix="/constraints", tags=["constraints"])


def _get_owned(db: Session, constraint_id: int, ident: Identity) -> Constraint:
    c = db.get(Constraint, constraint_id)
    if c is None or c.tenant_id != ident.tenant_id or c.user_id != ident.user_id:
        raise HTTPException(404, "Constraint not found")
    return c


@router.get("", response_model=list[ConstraintOut])
def list_constraints(
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> list[Constraint]:
    return list(
        db.scalars(
            select(Constraint)
            .where(
                Constraint.tenant_id == ident.tenant_id,
                Constraint.user_id == ident.user_id,
            )
            .order_by(Constraint.is_active.desc(), Constraint.created_at.desc())
        ).all()
    )


@router.post("", response_model=ConstraintOut, status_code=201)
def create_constraint(
    body: ConstraintCreate,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> Constraint:
    # Injuries default to deferring rehab to a professional unless overridden.
    defer = (
        body.defer_to_professional
        if body.defer_to_professional is not None
        else (body.kind == "injury")
    )
    c = Constraint(
        tenant_id=ident.tenant_id,
        user_id=ident.user_id,
        kind=body.kind,
        label=body.label.strip(),
        directives=body.directives,
        defer_to_professional=defer,
        is_active=body.is_active,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@router.patch("/{constraint_id}", response_model=ConstraintOut)
def update_constraint(
    constraint_id: int,
    body: ConstraintUpdate,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> Constraint:
    c = _get_owned(db, constraint_id, ident)
    data = body.model_dump(exclude_unset=True)
    if "kind" in data and data["kind"] is not None:
        c.kind = data["kind"]
    if "label" in data and data["label"] is not None:
        c.label = data["label"].strip()
    if "directives" in data:
        c.directives = data["directives"]
    if "defer_to_professional" in data and data["defer_to_professional"] is not None:
        c.defer_to_professional = data["defer_to_professional"]
    if "is_active" in data and data["is_active"] is not None:
        c.is_active = data["is_active"]
    db.commit()
    db.refresh(c)
    return c


@router.delete("/{constraint_id}", status_code=204)
def delete_constraint(
    constraint_id: int,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> Response:
    db.delete(_get_owned(db, constraint_id, ident))
    db.commit()
    return Response(status_code=204)
