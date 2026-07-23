"""Workout session / logging schemas."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from api.schemas.exercise import ExerciseBrief, ExercisePerformance

# Coarse terrain classes accepted for a route-capable activity (→ Pandolf
# terrain factor server-side).
Terrain = Literal["treadmill", "road", "trail", "offtrail", "snow"]

# How the route stats were entered — the flexible-input modes all land here.
# `health` = automatic capture from the phone's health store (HealthKit /
# Health Connect) via the Capacitor native shell (vires-ops#37); the load path
# (SI conversion + metabolic cost) is identical regardless of source.
RouteSource = Literal["manual", "route_search", "route_draw", "gpx", "health"]

# Coarse structured load vocabulary shared by every activity (retired from
# the former api.schemas.calendar_event — merge_calendar_events_into_activity).
LoadRegions = Literal["legs", "upper", "full", "core", "none"]
LoadIntensity = Literal["light", "moderate", "hard"]

# none | weekly. 'weekly' repeats every 7 days from the activity's own
# started_at date, expanded server-side on read — never persisted as extra
# rows (see api.services.recurrence).
Recurrence = Literal["none", "weekly"]


class WorkoutStart(BaseModel):
    template_id: int | None = None  # None => empty/ad-hoc workout
    name: str | None = None
    # Optional session context, settable at the moment of starting (also
    # editable later via PATCH): free-text tags/custom labels, including
    # what was eaten/drunk/supplemented pre-workout.
    tags: list[str] | None = None


class WorkoutFinish(BaseModel):
    """End-of-workout self-report, prompted when finishing. All optional so a
    user can just tap Finish and skip the rating; when given, each is a 1–10
    score: energy/readiness, how hard the session was (effort), and how
    appropriately challenging it was for the user's current level."""

    energy_level: int | None = Field(default=None, ge=1, le=10)
    workout_intensity: int | None = Field(default=None, ge=1, le=10)
    challenge_level: int | None = Field(default=None, ge=1, le=10)


class SetIn(BaseModel):
    reps: int | None = None
    weight: float | None = None
    rpe: float | None = None
    duration_seconds: int | None = None
    is_warmup: bool = False
    set_number: int | None = None  # auto-assigned (next) when omitted
    # Whether the new set is already performed. Defaults True (a directly-logged
    # set). The app passes False from "+ Add set" so an empty row appears unchecked
    # for the user to fill in and tick off themselves.
    done: bool = True
    # Client-generated UUID (crypto.randomUUID()) for offline-first logging
    # (vires-ops#48). Sent so a set queued offline and replayed on reconnect is
    # idempotent server-side — a duplicate replay returns the original row
    # instead of appending a second one. Omitted for plain online writes.
    client_uuid: str | None = None


class SetUpdate(BaseModel):
    reps: int | None = None
    weight: float | None = None
    rpe: float | None = None
    duration_seconds: int | None = None
    is_warmup: bool | None = None
    # Mark the set done/undone — stamps (or clears) completed_at server-side.
    done: bool | None = None


class SetOut(BaseModel):
    id: int
    set_number: int
    reps: int | None = None
    weight: float | None = None
    rpe: float | None = None
    duration_seconds: int | None = None
    is_warmup: bool = False
    completed_at: datetime | None = None
    # Echoed back so the client can reconcile a replayed offline write against
    # its IndexedDB queue entry (vires-ops#48).
    client_uuid: str | None = None


class SessionExerciseIn(BaseModel):
    exercise_id: int
    target_sets: int | None = None
    target_reps: int | None = None
    target_weight: float | None = None
    target_duration_seconds: int | None = None
    rest_seconds: int | None = None
    notes: str | None = None


class SessionExerciseUpdate(BaseModel):
    """Patch a session exercise in place: tweak its rest/targets, or set an
    explicit ``order_index`` directly (a single manual reposition). All
    fields optional; only those present (``exclude_unset``) are applied.
    A drag-and-drop reorder of the whole list goes through
    ``SessionExerciseReorder`` instead (one call, not N pairwise PATCHes).
    """

    target_sets: int | None = None
    target_reps: int | None = None
    target_weight: float | None = None
    target_duration_seconds: int | None = None
    rest_seconds: int | None = None
    notes: str | None = None
    order_index: int | None = None


class SessionExerciseReorder(BaseModel):
    """The session's exercises in their new order (drag-and-drop). Must be
    exactly the set of exercise ids currently on the session — ``order_index``
    is reassigned 0..n-1 from this list's position in one transaction."""

    exercise_ids: list[int] = Field(min_length=1)


class SessionExerciseReplace(BaseModel):
    """Swap an in-progress exercise for another, in place — the "replace"
    action. Keeps the slot's position (``order_index``) and set/rep/rest
    scheme, but retargets it to ``exercise_id`` and re-seeds fresh set rows
    for the new move (the old, exercise-specific weight/duration and any
    logged sets are discarded)."""

    exercise_id: int


class SessionExerciseOut(BaseModel):
    id: int
    order_index: int
    exercise: ExerciseBrief
    target_sets: int | None = None
    target_reps: int | None = None
    target_weight: float | None = None
    target_duration_seconds: int | None = None
    rest_seconds: int | None = None
    notes: str | None = None
    sets: list[SetOut]
    # Most recent prior performance of this exercise (the "last time" hint).
    previous_performance: ExercisePerformance | None = None


class ActivityTemplateOut(BaseModel):
    """One entry in the fixed activity-template catalog (``GET
    /workouts/activity-templates``) — a starting point the quick-log form
    prefills and the user can freely edit. ``route_capable`` templates
    (walk/run/hike) additionally get the route-capture UI + optional
    pack-weight section on the frontend."""

    key: str
    label: str
    regions: LoadRegions
    intensity: LoadIntensity
    route_capable: bool = False


# --------------------------------------------------------------------------- #
# Activity (cross-training + locomotion) — Tier 0 quick-log
# --------------------------------------------------------------------------- #
class ActivityLogIn(BaseModel):
    """Quick-log a completed activity — cross-training (climbing, swimming,
    yoga, ...) or locomotion (walk/run/hike). Route + load-carriage fields
    are optional on every template: only walk/run/hike surface their picker
    in the UI, but the backend doesn't gate on ``template_key`` (a custom
    entry could plausibly carry a route too).

    ``regions``/``intensity`` are always present — a template prefills them,
    but 'custom' (freeform, no template) still requires the user to pick a
    coarse estimate rather than leaving it unset, since that's the whole
    point of logging this: giving the coach something to reason about.

    Numbers arrive in the USER'S display units (weights in the account's
    ``weight_unit``; distance/elevation in mi/ft when that unit is ``lb``,
    km/m when ``kg``). The router converts to canonical SI once, at the
    boundary.

    Also covers what used to be a separate ``CalendarEvent`` create (a race,
    a weekly league game, a trip, a rehab window) — ``recurrence`` /
    ``event_end_date`` / ``objective_id`` / ``sport`` are the event-only
    axes. There is no separate "planned" flag: a future ``started_at``
    simply leaves ``ended_at`` null server-side (see
    ``api.routers.workouts.log_activity``) until the user later logs what
    happened.
    """

    name: str = Field(min_length=1, description="Display name, e.g. 'Indoor top-rope'")
    template_key: str = "custom"
    duration_s: int | None = Field(default=None, ge=0)
    regions: LoadRegions = "full"
    intensity: LoadIntensity = "moderate"
    # Optional backdate/future-date (e.g. logging yesterday's session, or
    # scheduling a future race). Defaults to now server-side.
    started_at: datetime | None = None

    # Event-merge fields (former CalendarEvent axes).
    sport: str | None = None
    recurrence: Recurrence = "none"
    # Last day of a multi-day activity (>= started_at's date); omit for a
    # single-day activity. Not supported alongside recurrence='weekly'.
    event_end_date: date | None = None
    # Set only when this activity IS itself a peak target an Objective
    # anchors to (e.g. the race).
    objective_id: int | None = None

    # Route capture — optional for every template.
    distance: float | None = Field(default=None, ge=0)
    elevation_gain: float | None = Field(default=None, ge=0)
    terrain: Terrain = "trail"
    # Which input mode produced the route stats (manual entry, trail search,
    # drawn route, or GPX import). Distance/elevation are always user-editable
    # regardless of source.
    source: RouteSource = "manual"

    # Optional load-carriage. Never required to submit — "i don't expect
    # people with light packs to bother weighing their pack" is the product
    # call here. bodyweight is required IFF pack_weight is given: Pandolf's
    # load ratio (L/W) is undefined without body mass, but bodyweight alone
    # with no pack is meaningless and simply ignored.
    pack_weight: float | None = Field(
        default=None, gt=0, description="Carried load, in the user's weight unit"
    )
    bodyweight: float | None = Field(
        default=None, gt=0, description="Body mass, in the user's weight unit"
    )

    @model_validator(mode="after")
    def _bodyweight_required_with_pack(self) -> ActivityLogIn:
        if self.pack_weight is not None and self.bodyweight is None:
            raise ValueError("bodyweight is required when pack_weight is given")
        return self

    @model_validator(mode="after")
    def _event_fields_consistent(self) -> ActivityLogIn:
        if self.recurrence == "weekly" and self.event_end_date is not None:
            raise ValueError("event_end_date is not supported for a weekly recurrence")
        # A None started_at defaults to "now" server-side (api.routers.
        # workouts.log_activity) — validated there against the resolved
        # value, since "now" isn't known at schema-validation time.
        if (
            self.event_end_date is not None
            and self.started_at is not None
            and self.event_end_date < self.started_at.date()
        ):
            raise ValueError("event_end_date must be on or after the start date")
        return self


class ActivityDetailOut(BaseModel):
    template_key: str = "custom"
    duration_s: int | None = None
    regions: LoadRegions
    intensity: LoadIntensity
    pack_weight_kg: float | None = None
    bodyweight_kg: float | None = None
    distance_m: float | None = None
    elevation_gain_m: float | None = None
    terrain: str = "trail"
    metabolic_cost_kj: float | None = None
    source: str = "manual"
    # Former CalendarEvent axes.
    sport: str | None = None
    event_end_date: date | None = None
    recurrence: Recurrence = "none"
    objective_id: int | None = None


class WorkoutSessionOut(BaseModel):
    id: int
    session_type: str = "strength"
    name: str | None = None
    started_at: datetime
    ended_at: datetime | None = None
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)
    energy_level: int | None = None
    workout_intensity: int | None = None
    challenge_level: int | None = None
    template_id: int | None = None
    exercises: list[SessionExerciseOut]
    # Present only for session_type == 'activity'.
    activity: ActivityDetailOut | None = None
    # Set only on a materialized occurrence of a recurring activity — the id
    # of the recurring "template" session it was expanded from.
    recurrence_source_id: int | None = None


class WorkoutSessionUpdate(BaseModel):
    """Partial update to a session (``exclude_unset`` — only supplied fields
    are applied). In practice activity-only today: a strength session is
    edited via its exercise/set sub-resources, not this endpoint.

    Serves BOTH "edit a still-open future/planned activity" and "log what
    actually happened on one" — the only difference is whether ``ended_at``
    is included. Setting it is what closes the row out; there's no separate
    status transition. Re-opening a closed session (``ended_at`` back to
    null) isn't supported here — omitted/null under ``exclude_unset`` are
    indistinguishable, so this endpoint is additive-only on ``ended_at``.
    """

    name: str | None = Field(default=None, min_length=1)
    started_at: datetime | None = None
    ended_at: datetime | None = None
    notes: str | None = None

    # Session-tracking fields — apply to any session type (strength or
    # activity), unlike the activity-only block below. ``tags`` replaces the
    # whole list when supplied; the 1–10 ratings can be revised after the fact.
    tags: list[str] | None = None
    energy_level: int | None = Field(default=None, ge=1, le=10)
    workout_intensity: int | None = Field(default=None, ge=1, le=10)
    challenge_level: int | None = Field(default=None, ge=1, le=10)

    # Activity-detail fields — rejected (400) if the session isn't
    # session_type == 'activity'.
    template_key: str | None = None
    duration_s: int | None = Field(default=None, ge=0)
    regions: LoadRegions | None = None
    intensity: LoadIntensity | None = None
    distance: float | None = Field(default=None, ge=0)
    elevation_gain: float | None = Field(default=None, ge=0)
    terrain: Terrain | None = None
    source: RouteSource | None = None
    pack_weight: float | None = Field(default=None, gt=0)
    bodyweight: float | None = Field(default=None, gt=0)

    # Event-merge fields.
    sport: str | None = None
    recurrence: Recurrence | None = None
    event_end_date: date | None = None
    objective_id: int | None = None

    @model_validator(mode="after")
    def _bodyweight_required_with_pack(self) -> WorkoutSessionUpdate:
        if self.pack_weight is not None and self.bodyweight is None:
            raise ValueError("bodyweight is required when pack_weight is given")
        return self

    @model_validator(mode="after")
    def _recurrence_end_date_exclusive(self) -> WorkoutSessionUpdate:
        if self.recurrence == "weekly" and self.event_end_date is not None:
            raise ValueError("event_end_date is not supported for a weekly recurrence")
        return self


class MaterializeOccurrenceIn(BaseModel):
    """Turn one virtual (expanded-on-read, never-persisted) occurrence of a
    recurring activity into a real, linked row — see
    ``api.routers.workouts.materialize_occurrence``."""

    occurrence_date: date


class WorkoutSummary(BaseModel):
    id: int
    session_type: str = "strength"
    name: str | None = None
    started_at: datetime
    ended_at: datetime | None = None
    exercise_count: int
    set_count: int
    total_volume: float = Field(
        default=0.0, description="Sum of reps*weight over completed working sets"
    )
    # Session-tracking summary bits surfaced on the history row.
    tags: list[str] = Field(default_factory=list)
    energy_level: int | None = None
    workout_intensity: int | None = None
    challenge_level: int | None = None
    # Compact activity facts for the history row (None otherwise).
    activity: ActivityDetailOut | None = None
