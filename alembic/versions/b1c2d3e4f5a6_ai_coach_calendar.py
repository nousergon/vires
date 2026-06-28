"""AI coach calendar: planned_workouts + planned_exercises, program fields,
repoint the workout_sessions seam, drop the unused relative-grid program tables.

Revision ID: b1c2d3e4f5a6
Revises: 1d821b911adb
Create Date: 2026-06-28

The old Program -> ProgramWeek -> ProgramSlot grid was a relative (week/day)
seam with no absolute dates and no rows/UI — the wrong shape for a calendar.
It is replaced here by date-bearing PlannedWorkout/PlannedExercise. Because the
program_slots / program_weeks / programs tables were empty, this is a clean
structural swap (no data migration). workout_sessions DOES carry data, so its
seam column is altered in place via batch mode (data preserved).

NOTE: alembic autogenerate would also propose dropping the exercises_fts* tables
— those are SQLite FTS5 shadow tables (managed by api/db/fts.py, not the ORM).
Intentionally omitted.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "1d821b911adb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Extend programs with the coach fields. (Table is empty; server_default
    #    on status keeps the NOT NULL safe regardless.)
    with op.batch_alter_table("programs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("goal_text", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("spec", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("start_date", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("end_date", sa.Date(), nullable=True))
        batch_op.add_column(
            sa.Column("status", sa.String(), nullable=False, server_default="active")
        )
    op.create_index("ix_programs_status", "programs", ["status"])

    # 2. planned_workouts — the calendar's future unit. Created BEFORE altering
    #    workout_sessions so the seam FK target exists; empty at creation so the
    #    workout_sessions batch-recreate below sees no rows referencing it.
    op.create_table(
        "planned_workouts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("program_id", sa.Integer(), nullable=True),
        sa.Column("template_id", sa.Integer(), nullable=True),
        sa.Column("scheduled_date", sa.Date(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("week_index", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="planned"),
        sa.Column("created_by", sa.String(), nullable=False, server_default="coach"),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_id"], ["workout_templates.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["workout_sessions.id"]),
    )
    op.create_index(
        "ix_planned_workouts_scheduled_date", "planned_workouts", ["scheduled_date"]
    )
    op.create_index("ix_planned_workouts_user_id", "planned_workouts", ["user_id"])
    op.create_index("ix_planned_workouts_tenant_id", "planned_workouts", ["tenant_id"])
    op.create_index("ix_planned_workouts_program_id", "planned_workouts", ["program_id"])
    op.create_index("ix_planned_workouts_status", "planned_workouts", ["status"])

    # 3. planned_exercises — per-day prescription.
    op.create_table(
        "planned_exercises",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("planned_workout_id", sa.Integer(), nullable=False),
        sa.Column("exercise_id", sa.Integer(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("target_sets", sa.Integer(), nullable=True),
        sa.Column("target_reps", sa.Integer(), nullable=True),
        sa.Column("target_weight", sa.Float(), nullable=True),
        sa.Column("target_duration_seconds", sa.Integer(), nullable=True),
        sa.Column("rest_seconds", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["planned_workout_id"], ["planned_workouts.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["exercise_id"], ["exercises.id"]),
    )
    op.create_index(
        "ix_planned_exercises_planned_workout_id",
        "planned_exercises",
        ["planned_workout_id"],
    )
    op.create_index(
        "ix_planned_exercises_exercise_id", "planned_exercises", ["exercise_id"]
    )

    # 4. Repoint the workout_sessions seam: program_slot_id -> planned_workout_id.
    #    (Data preserved; the old FK column had no rows pointing anywhere useful.)
    with op.batch_alter_table("workout_sessions", schema=None) as batch_op:
        batch_op.drop_column("program_slot_id")
        batch_op.add_column(sa.Column("planned_workout_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_workout_sessions_planned_workout_id",
            "planned_workouts",
            ["planned_workout_id"],
            ["id"],
        )

    # 5. Drop the unused relative-grid tables.
    op.drop_table("program_slots")
    op.drop_table("program_weeks")


def downgrade() -> None:
    # Recreate the relative-grid tables (empty) and reverse the rest.
    op.create_table(
        "program_weeks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("program_id", sa.Integer(), nullable=False),
        sa.Column("week_index", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "program_slots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("program_week_id", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=True),
        sa.Column("day_index", sa.Integer(), nullable=True),
        sa.Column("progression_rule", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["program_week_id"], ["program_weeks.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["template_id"], ["workout_templates.id"]),
    )

    with op.batch_alter_table("workout_sessions", schema=None) as batch_op:
        batch_op.drop_column("planned_workout_id")
        batch_op.add_column(sa.Column("program_slot_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_workout_sessions_program_slot_id",
            "program_slots",
            ["program_slot_id"],
            ["id"],
        )

    op.drop_index("ix_planned_exercises_exercise_id", table_name="planned_exercises")
    op.drop_index(
        "ix_planned_exercises_planned_workout_id", table_name="planned_exercises"
    )
    op.drop_table("planned_exercises")

    for ix in (
        "ix_planned_workouts_status",
        "ix_planned_workouts_program_id",
        "ix_planned_workouts_tenant_id",
        "ix_planned_workouts_user_id",
        "ix_planned_workouts_scheduled_date",
    ):
        op.drop_index(ix, table_name="planned_workouts")
    op.drop_table("planned_workouts")

    op.drop_index("ix_programs_status", table_name="programs")
    with op.batch_alter_table("programs", schema=None) as batch_op:
        batch_op.drop_column("status")
        batch_op.drop_column("end_date")
        batch_op.drop_column("start_date")
        batch_op.drop_column("spec")
        batch_op.drop_column("goal_text")
