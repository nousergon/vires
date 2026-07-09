"""AI coach: generate a multi-week program from a natural-language request.

``POST /coach/generate`` runs the LLM (grounded, forced tool-use) -> validated
``ProgramSpec`` -> deterministic materialization, and returns a NON-persisted
preview. ``POST /coach/programs`` re-materializes the confirmed spec server-side
(single source of truth) and persists it. Refine = resend ``prior_spec``.
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.config import get_settings
from api.db.identity import Identity, current_identity
from api.db.models import (
    PlanChangeEvent,
    PlannedExercise,
    PlannedWorkout,
    Program,
    TemplateExercise,
    WorkoutTemplate,
)
from api.db.session import get_db
from api.schemas.coach import (
    CreatedRoutinePreview,
    GenerateRequest,
    ModifyRequest,
    PlanChangeEventOut,
    PlannedExercisePreview,
    PlannedWorkoutPreview,
    ProgramModifyPreview,
    ProgramPreview,
    ProgramSpec,
    ReplanCheckOut,
    ReplanProposal,
    ReplanTriggerOut,
    SaveProgramRequest,
    TranscribeOut,
)
from api.schemas.plan import ProgramOut
from api.serializers import to_program_out
from api.services.coach.agent import CoachError, CoachUnavailable, generate_spec
from api.services.coach.audit import record_plan_change
from api.services.coach.context import (
    build_coach_objective_context,
    build_materialize_context,
    exercise_meta_for_ids,
)
from api.services.coach.materialize import (
    ExerciseMeta,
    MaterializeContext,
    end_date,
    materialize,
    rewrite_routine_refs,
    start_date_of,
    synthesize_routines,
)
from api.services.coach.replan import detect_triggers, replan_instruction
from api.services.objective_focus import resolve_focus_objective
from api.services.stt import STTError, transcribe_audio

MAX_AUDIO_BYTES = 25 * 1024 * 1024  # 25 MB — the Whisper API per-file limit

router = APIRouter(prefix="/coach", tags=["coach"])


def _spec_exercise_meta(db: Session, spec: ProgramSpec) -> ExerciseMeta:
    """name + is_timed for every exercise the spec's authored routines reference."""
    ids = {e.exercise_id for r in spec.new_routines for e in r.exercises}
    return exercise_meta_for_ids(db, ids)


def _build_preview(spec: ProgramSpec, ctx: MaterializeContext, db: Session) -> ProgramPreview:
    # Authored routines are folded in as synthetic templates so the preview
    # materializes them without persisting anything (save creates them for real).
    meta = _spec_exercise_meta(db, spec)
    mat_spec, mat_ctx = synthesize_routines(spec, ctx, meta)
    workouts = materialize(mat_spec, mat_ctx)
    created = [
        CreatedRoutinePreview(
            key=r.key,
            name=r.name,
            exercise_names=[
                meta.get(e.exercise_id, (f"#{e.exercise_id}", False))[0]
                for e in r.exercises
            ],
        )
        for r in spec.new_routines
    ]
    return ProgramPreview(
        name=spec.name,
        coach_summary=spec.coach_summary,
        start_date=start_date_of(spec),
        end_date=end_date(spec),
        weight_unit=ctx.weight_unit,
        spec=spec,
        created_routines=created,
        planned_workouts=[
            PlannedWorkoutPreview(
                template_id=pw.template_id,
                scheduled_date=pw.scheduled_date,
                name=pw.name,
                week_index=pw.week_index,
                exercises=[
                    PlannedExercisePreview(
                        exercise_id=e.exercise_id,
                        exercise_name=e.exercise_name,
                        order_index=e.order_index,
                        target_sets=e.target_sets,
                        target_reps=e.target_reps,
                        target_weight=e.target_weight,
                        target_duration_seconds=e.target_duration_seconds,
                        rest_seconds=e.rest_seconds,
                        notes=e.notes,
                    )
                    for e in pw.exercises
                ],
            )
            for pw in workouts
        ],
    )


@router.post("/generate", response_model=ProgramPreview)
def generate(
    body: GenerateRequest,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> ProgramPreview:
    ctx = build_materialize_context(db, ident)
    obj_ctx = build_coach_objective_context(db, ident)
    # The coach needs SOMETHING to work with: existing routines, or an objective
    # whose catalog candidates let it author new routines.
    if not ctx.templates and not obj_ctx.candidates:
        raise HTTPException(
            400, "Create a routine or set an objective before asking the coach."
        )
    try:
        spec = generate_spec(body.message, ctx, date.today(), body.prior_spec, obj_ctx)
    except CoachUnavailable as e:
        raise HTTPException(503, str(e)) from e
    except CoachError as e:
        raise HTTPException(502, f"Coach could not build a plan: {e}") from e
    return _build_preview(spec, ctx, db)


@router.post("/transcribe", response_model=TranscribeOut)
async def transcribe(
    request: Request,
    ident: Identity = Depends(current_identity),
) -> TranscribeOut:
    """Speak-to-the-coach: raw audio body -> Whisper -> text to drop in the box.

    Audio arrives as the raw request body (Content-Type from the recorder), so no
    multipart parsing is needed server-side. No key => 503 (mic hidden client-side).
    """
    if not get_settings().stt_api_key:
        raise HTTPException(503, "Speech-to-text is not configured.")
    audio = await request.body()
    if not audio:
        raise HTTPException(400, "Empty audio.")
    if len(audio) > MAX_AUDIO_BYTES:
        raise HTTPException(413, "Audio too large (max 25 MB).")
    content_type = request.headers.get("content-type") or "audio/webm"
    try:
        text = await transcribe_audio(audio, content_type)
    except STTError as e:
        raise HTTPException(502, f"Transcription failed: {e}") from e
    return TranscribeOut(text=text)


def _persist_new_routines(db: Session, ident: Identity, spec: ProgramSpec) -> ProgramSpec:
    """Persist the coach's authored routines as reusable WorkoutTemplates and
    return the spec with ``routine_key`` refs rewritten to the new real ids
    (``new_routines`` cleared). No-op when the spec authored none."""
    if not spec.new_routines:
        return spec
    # Validate every authored exercise id exists before creating anything.
    ref_ids = {e.exercise_id for r in spec.new_routines for e in r.exercises}
    known = exercise_meta_for_ids(db, ref_ids)
    missing = ref_ids - known.keys()
    if missing:
        raise HTTPException(400, f"Unknown exercise_id(s) in routine: {sorted(missing)}")

    key_to_id: dict[str, int] = {}
    for r in spec.new_routines:
        tpl = WorkoutTemplate(
            tenant_id=ident.tenant_id,
            user_id=ident.user_id,
            name=r.name.strip(),
            exercises=[
                TemplateExercise(
                    exercise_id=e.exercise_id,
                    order_index=i,
                    target_sets=e.sets,
                    target_reps=e.reps,
                    target_weight=e.weight,
                    target_duration_seconds=e.duration_seconds,
                    rest_seconds=e.rest_seconds,
                )
                for i, e in enumerate(r.exercises)
            ],
        )
        db.add(tpl)
        db.flush()  # assign tpl.id
        key_to_id[r.key] = tpl.id
    return rewrite_routine_refs(spec, key_to_id)


def _active_objective_id(db: Session, ident: Identity) -> int | None:
    """The derived focus objective for this user (the plan trains for it)."""
    focus = resolve_focus_objective(db, ident)
    return focus.id if focus is not None else None


@router.post("/programs", response_model=ProgramOut, status_code=201)
def save_program(
    body: SaveProgramRequest,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> ProgramOut:
    # Create any authored routines first, then materialize against a context that
    # now includes them (so their schedule entries resolve to real templates).
    spec = _persist_new_routines(db, ident, body.spec)
    ctx = build_materialize_context(db, ident)
    rows = _materialize_rows(spec, ctx, ident)
    if not rows:
        raise HTTPException(400, "Spec produced no workouts (unknown templates?).")

    # Deactivate any other active programs: keep completed workouts, drop future
    # ones (same semantics as apply_program's cutover). A user has at most one
    # live plan; regenerating creates a new program, not a parallel one.
    old_active = db.scalars(
        select(Program).where(
            Program.tenant_id == ident.tenant_id,
            Program.user_id == ident.user_id,
            Program.status == "active",
        )
    ).all()
    for old in old_active:
        old.status = "superseded"
        # Remove future (non-completed) workouts — they belong to the superseded plan.
        old.planned_workouts = [
            pw for pw in old.planned_workouts if pw.status == "completed"
        ]

    program = Program(
        tenant_id=ident.tenant_id,
        user_id=ident.user_id,
        name=(body.name or spec.name).strip(),
        # Link the plan to the objective it trains for (the coach's strategy is in
        # spec.coach_summary), so the active strategy can be shown on the objective.
        objective_id=_active_objective_id(db, ident),
        goal_text=body.goal_text,
        spec=spec.model_dump(mode="json"),
        start_date=start_date_of(spec),
        end_date=end_date(spec),
        status="active",
        planned_workouts=rows,
    )
    db.add(program)
    db.commit()
    db.refresh(program)
    return to_program_out(program)


# --------------------------------------------------------------------------- #
# modification (reschedule / regenerate an existing program)
# --------------------------------------------------------------------------- #
def _materialize_rows(
    spec: ProgramSpec,
    ctx: MaterializeContext,
    ident: Identity,
    since: date | None = None,
) -> list[PlannedWorkout]:
    """Materialize the spec into PlannedWorkout ORM rows (optionally only on/after
    ``since`` — used when applying a modification to preserve completed history)."""
    rows: list[PlannedWorkout] = []
    for pw in materialize(spec, ctx):
        if since is not None and pw.scheduled_date < since:
            continue
        rows.append(
            PlannedWorkout(
                tenant_id=ident.tenant_id,
                user_id=ident.user_id,
                template_id=pw.template_id,
                objective_id=pw.objective_id,
                scheduled_date=pw.scheduled_date,
                name=pw.name,
                week_index=pw.week_index,
                status="planned",
                created_by="coach",
                exercises=[
                    PlannedExercise(
                        exercise_id=e.exercise_id,
                        order_index=e.order_index,
                        target_sets=e.target_sets,
                        target_reps=e.target_reps,
                        target_weight=e.target_weight,
                        target_duration_seconds=e.target_duration_seconds,
                        rest_seconds=e.rest_seconds,
                        notes=e.notes,
                    )
                    for e in pw.exercises
                ],
            )
        )
    return rows


def _get_owned_program(db: Session, program_id: int, ident: Identity) -> Program:
    p = db.get(Program, program_id)
    if p is None or p.tenant_id != ident.tenant_id or p.user_id != ident.user_id:
        raise HTTPException(404, "Program not found")
    return p


def _program_spec(program: Program) -> ProgramSpec:
    if not program.spec:
        raise HTTPException(400, "This program has no editable coach spec.")
    return ProgramSpec.model_validate(program.spec)


def _cutover(program: Program, today: date) -> date:
    """First date a re-plan may occupy: today, or the day after the last completed
    workout — so applying a change never duplicates a day already trained."""
    completed = [pw.scheduled_date for pw in program.planned_workouts if pw.status == "completed"]
    return max([today, *(d + timedelta(days=1) for d in completed)])


def _modify_preview(
    db: Session, ident: Identity, program: Program, message: str
) -> ProgramModifyPreview:
    """Run the LLM modify against a program's stored spec and build the
    non-persisted cutover preview. Shared by manual modify + auto re-plan."""
    prior = _program_spec(program)
    ctx = build_materialize_context(db, ident)
    obj_ctx = build_coach_objective_context(db, ident)
    try:
        new_spec = generate_spec(
            message, ctx, date.today(), prior_spec=prior, obj_ctx=obj_ctx
        )
    except CoachUnavailable as e:
        raise HTTPException(503, str(e)) from e
    except CoachError as e:
        raise HTTPException(502, f"Coach could not modify the plan: {e}") from e

    cutover = _cutover(program, date.today())
    completed = sum(1 for pw in program.planned_workouts if pw.status == "completed")
    # Count future days against the synthesized spec so authored routines expand.
    mat_spec, mat_ctx = synthesize_routines(new_spec, ctx, _spec_exercise_meta(db, new_spec))
    future = sum(1 for pw in materialize(mat_spec, mat_ctx) if pw.scheduled_date >= cutover)
    return ProgramModifyPreview(
        program_id=program.id,
        preview=_build_preview(new_spec, ctx, db),
        completed_preserved=completed,
        future_count=future,
    )


@router.post("/programs/{program_id}/modify", response_model=ProgramModifyPreview)
def modify_program(
    program_id: int,
    body: ModifyRequest,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> ProgramModifyPreview:
    """Preview a NL change to a program. The coach edits the stored spec (refine
    against prior_spec); nothing is persisted until PUT /coach/programs/{id}."""
    program = _get_owned_program(db, program_id, ident)
    return _modify_preview(db, ident, program, body.message)


@router.get("/programs/{program_id}/replan-check", response_model=ReplanCheckOut)
def replan_check(
    program_id: int,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> ReplanCheckOut:
    """Cheap (no-LLM) check for whether a structural re-plan is suggested — the UI
    calls this (e.g. after a workout / on opening the plan) to decide whether to
    offer a re-plan before paying for the proposal."""
    program = _get_owned_program(db, program_id, ident)
    triggers = detect_triggers(db, ident, program, date.today())
    return ReplanCheckOut(
        suggested=bool(triggers),
        triggers=[ReplanTriggerOut(kind=t.kind, reason=t.reason) for t in triggers],
    )


@router.post("/programs/{program_id}/replan", response_model=ReplanProposal)
def replan_program(
    program_id: int,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> ReplanProposal:
    """Propose an auto re-plan when a structural trigger has fired. Generates (but
    does NOT persist) an updated plan from a synthesized instruction; the user
    applies it via PUT /coach/programs/{id} (propose-and-confirm, never silent)."""
    program = _get_owned_program(db, program_id, ident)
    today = date.today()
    triggers = detect_triggers(db, ident, program, today)
    if not triggers:
        raise HTTPException(409, "No re-plan is currently suggested for this program.")
    preview = _modify_preview(db, ident, program, replan_instruction(triggers, today))
    return ReplanProposal(
        triggers=[ReplanTriggerOut(kind=t.kind, reason=t.reason) for t in triggers],
        modification=preview,
    )


@router.put("/programs/{program_id}", response_model=ProgramOut)
def apply_program(
    program_id: int,
    body: SaveProgramRequest,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> ProgramOut:
    """Apply a (modified) spec: freeze completed workouts, replace every future
    (not-yet-done) one with the new materialization from today onward."""
    program = _get_owned_program(db, program_id, ident)
    # Persist any newly-authored routines, then materialize against a context
    # that includes them.
    spec = _persist_new_routines(db, ident, body.spec)
    ctx = build_materialize_context(db, ident)
    cutover = _cutover(program, date.today())

    # Keep completed history; everything else (planned/skipped) is replaced from
    # the cutover forward (never re-adding an already-trained day).
    kept = [pw for pw in program.planned_workouts if pw.status == "completed"]
    new_future = _materialize_rows(spec, ctx, ident, since=cutover)
    program.planned_workouts = kept + new_future  # delete-orphan drops the rest

    program.spec = spec.model_dump(mode="json")
    if body.name:
        program.name = body.name.strip()
    program.start_date = start_date_of(spec)
    program.end_date = end_date(spec)
    record_plan_change(
        db,
        ident,
        source="plan_revision",
        program_id=program.id,
        summary=(
            f"Plan revised: {len(kept)} completed workout(s) kept, "
            f"{len(new_future)} upcoming workout(s) rescheduled."
        ),
        detail={"completed_preserved": len(kept), "future_count": len(new_future)},
    )
    db.commit()
    db.refresh(program)
    return to_program_out(program)


@router.get("/programs/{program_id}/changes", response_model=list[PlanChangeEventOut])
def list_plan_changes(
    program_id: int,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> list[PlanChangeEvent]:
    """The plan-change audit trail for a program (most recent first) — answers
    'why did my plan change?' across both the autoregulation and revision loops."""
    _get_owned_program(db, program_id, ident)  # ownership check (404 if not yours)
    return list(
        db.scalars(
            select(PlanChangeEvent)
            .where(
                PlanChangeEvent.tenant_id == ident.tenant_id,
                PlanChangeEvent.user_id == ident.user_id,
                PlanChangeEvent.program_id == program_id,
            )
            .order_by(PlanChangeEvent.created_at.desc(), PlanChangeEvent.id.desc())
        ).all()
    )
