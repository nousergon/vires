"""Seed a real objective + constraint for the dev user (objective-driven coach).

    uv run python -m api.db.seed_objective --target-date 2026-09-05
    uv run python -m api.db.seed_objective --target-date 2026-09-05 --name "Climb Baker"

Idempotent: re-running updates the same-named objective + the injury constraint
in place (so you can re-point the summit date without piling up duplicates).
Defaults seed the build-spec case: a dated alpine "Climb Baker" primary
objective + a "recovering L4-L5 disc" injury constraint. The objective carries
the authored alpine needs-analysis; the constraint carries the lumbar-disc
directives — both as DATA the coach consumes.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

from sqlalchemy import select

from api.db.identity import Identity, ensure_dev_identity
from api.db.models import Constraint, Objective
from api.db.session import SessionLocal
from api.services.coach.objective_profiles import (
    ALPINE_DEMANDS_PROFILE,
    LUMBAR_DISC_DIRECTIVES,
)

DEFAULT_NAME = "Climb Baker"
DEFAULT_SPORT = "alpine"
DISC_LABEL = "recovering L4-L5 disc"


def _upsert_objective(session, ident: Identity, name: str, target: date) -> Objective:
    obj = session.scalar(
        select(Objective).where(
            Objective.tenant_id == ident.tenant_id,
            Objective.user_id == ident.user_id,
            Objective.name == name,
        )
    )
    if obj is None:
        obj = Objective(tenant_id=ident.tenant_id, user_id=ident.user_id, name=name)
        session.add(obj)
    obj.kind = "dated"
    obj.target_date = target
    obj.sport = DEFAULT_SPORT
    obj.demands_profile = ALPINE_DEMANDS_PROFILE
    obj.is_primary = True
    return obj


def _upsert_disc_constraint(session, ident: Identity) -> Constraint:
    con = session.scalar(
        select(Constraint).where(
            Constraint.tenant_id == ident.tenant_id,
            Constraint.user_id == ident.user_id,
            Constraint.label == DISC_LABEL,
        )
    )
    if con is None:
        con = Constraint(
            tenant_id=ident.tenant_id, user_id=ident.user_id, label=DISC_LABEL
        )
        session.add(con)
    con.kind = "injury"
    con.directives = LUMBAR_DISC_DIRECTIVES
    con.defer_to_professional = True
    con.is_active = True
    return con


def seed_objective(target_date: date, name: str = DEFAULT_NAME) -> None:
    with SessionLocal() as session:
        ident = ensure_dev_identity(session)
        # Demote any other primary so the one-primary invariant holds.
        for other in session.scalars(
            select(Objective).where(
                Objective.tenant_id == ident.tenant_id,
                Objective.user_id == ident.user_id,
                Objective.is_primary.is_(True),
                Objective.name != name,
            )
        ).all():
            other.is_primary = False
        session.flush()

        obj = _upsert_objective(session, ident, name, target_date)
        con = _upsert_disc_constraint(session, ident)
        session.commit()
        print(
            f"Seeded objective '{obj.name}' (alpine, target {obj.target_date}, "
            f"primary) + constraint '{con.label}' (injury, defer-to-PT)."
        )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Seed the dev objective + constraint.")
    p.add_argument(
        "--target-date",
        required=True,
        help="objective peak/summit date, ISO YYYY-MM-DD (e.g. 2026-09-05)",
    )
    p.add_argument("--name", default=DEFAULT_NAME, help=f"objective name (default: {DEFAULT_NAME})")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    try:
        target = date.fromisoformat(args.target_date)
    except ValueError as e:
        raise SystemExit(
            f"--target-date must be ISO YYYY-MM-DD, got {args.target_date!r}"
        ) from e
    seed_objective(target, name=args.name)


if __name__ == "__main__":
    main()
