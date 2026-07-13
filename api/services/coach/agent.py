"""The coach LLM call: grounded, forced structured output.

A single Anthropic Messages call with a **forced** tool choice makes the model
emit a ``ProgramSpec`` (validated by Pydantic) rather than free text we'd have to
parse — the institutional pattern (structured tool-use over ``json.loads``). The
model is *grounded*: it only ever sees, and may only reference, the user's real
template/exercise ids. It proposes a declarative spec (schedule + curves); the
deterministic materializer does the arithmetic.
"""

from __future__ import annotations

import json
import logging
from datetime import date

from api.config import get_settings
from api.schemas.coach import ProgramSpec
from api.services.coach.materialize import (
    MaterializeContext,
    all_progressions,
    all_schedule,
)
from api.services.coach.objective_context import CoachObjectiveContext
from api.services.coach.prompt_loader import load_system_prompt

logger = logging.getLogger(__name__)

TOOL_NAME = "emit_program_spec"

# The system prompt is loaded at call time — tuned-private if hydrated onto the
# box, else the committed public baseline (see prompt_loader). The prompt is the
# Vires coaching edge, so its tuned form is NOT in this public repo.


class CoachUnavailable(RuntimeError):
    """Raised when the coach can't run (no API key). Router maps this to HTTP 503."""


class CoachError(RuntimeError):
    """The model failed to produce a usable spec after retry."""


def _weeks_until(target_date: date | None, today: date) -> int | None:
    """Whole weeks from ``today`` to ``target_date`` (>= 0), or None if undated."""
    if target_date is None:
        return None
    return max(0, (target_date - today).days // 7)


def _objective_block(obj_ctx: CoachObjectiveContext | None, today: date) -> dict | None:
    """The objective + active constraints the program must peak/taper to and
    train around (None when the user hasn't set an objective or constraints).

    When the athlete holds multiple dated peaks, ``timeline`` carries them all so
    the coach periodizes toward the next (``objective``) and base-builds for the
    rest."""
    if obj_ctx is None or obj_ctx.is_empty:
        return None
    block: dict = {}
    obj = obj_ctx.objective
    if obj is not None:
        block["objective"] = {
            "objective_id": obj.id,
            "name": obj.name,
            "kind": obj.kind,
            "target_date": obj.target_date.isoformat() if obj.target_date else None,
            "event_end_date": obj.event_end_date.isoformat()
            if obj.event_end_date
            else None,
            "weeks_until_target": _weeks_until(obj.target_date, today),
            "sport": obj.sport,
            "demands_profile": obj.demands_profile,
        }
        # Training milestones (sub-objectives) inside this block: dated benchmarks
        # the coach should periodize a mini-taper + retest around, then resume the
        # build toward the peak. NOT separate peaks — they serve the parent.
        if obj.milestones:
            block["objective"]["milestones"] = [
                {
                    "objective_id": m.id,
                    "name": m.name,
                    "target_date": m.target_date.isoformat()
                    if m.target_date
                    else None,
                    "weeks_until_target": _weeks_until(m.target_date, today),
                    "sport": m.sport,
                    "note": (
                        "training milestone within this objective's block — "
                        "taper lightly into it, treat the result as a fitness "
                        "checkpoint, then resume the build toward the peak"
                    ),
                }
                for m in obj.milestones
            ]
    # Only emit the timeline when there's genuinely more than one dated peak —
    # for a single objective it is redundant with "objective". Each entry carries
    # objective_id + event_end_date so the coach can build a season phase per peak.
    if len(obj_ctx.timeline) >= 2:
        block["timeline"] = [
            {
                "objective_id": peak.id,
                "name": peak.name,
                "target_date": peak.target_date.isoformat()
                if peak.target_date
                else None,
                "event_end_date": peak.event_end_date.isoformat()
                if peak.event_end_date
                else None,
                "weeks_until_target": _weeks_until(peak.target_date, today),
                "sport": peak.sport,
            }
            for peak in obj_ctx.timeline
        ]
    if obj_ctx.constraints:
        block["constraints"] = [
            {
                "kind": c.kind,
                "label": c.label,
                "directives": c.directives,
                "defer_to_professional": c.defer_to_professional,
            }
            for c in obj_ctx.constraints
        ]
    # Upcoming athletic events (recurrence-expanded, soonest first): load the
    # coach debits from the week's recovery budget and schedules *around* — never
    # a goal. An event anchored to an objective_id rides that objective's taper
    # instead of counting as a separate load constraint.
    if obj_ctx.events:
        block["events"] = [
            {
                "name": e.name,
                "template_key": e.template_key,
                "sport": e.sport,
                "date": e.occurrence_date.isoformat(),
                "end_date": e.occurrence_end_date.isoformat()
                if e.occurrence_end_date
                else None,
                "weeks_away": _weeks_until(e.occurrence_date, today),
                "recurrence": e.recurrence,
                "load": e.load,
                "objective_id": e.objective_id,
                "notes": e.notes,
                "note": (
                    "athletic event trained AROUND (a load constraint, not a "
                    "goal): debit its load.regions from that week's recovery "
                    "budget — do NOT stack heavy same-region work in the day or "
                    "two on either side; auto-lighten or insert recovery "
                    "adjacent to it. A 'weekly' recurrence is a standing weekly "
                    "load — bake its debit into the base template. If "
                    "objective_id is set, it rides that objective's taper."
                ),
            }
            for e in obj_ctx.events
        ]
    # Recently logged activities (climbing, swimming, yoga, walk/run/hike, ...),
    # most recent first: load ALREADY ABSORBED (distinct from `events`, which is
    # upcoming load to train around) — factor into today's fatigue/recovery.
    if obj_ctx.recent_activities:
        block["recent_activities"] = [
            {
                "name": a.name,
                "date": a.session_date.isoformat(),
                "days_ago": (today - a.session_date).days,
                "regions": a.regions,
                "intensity": a.intensity,
                "duration_min": a.duration_min,
                # Present only when logged with a weighted pack — regions/
                # intensity alone under-represent load-carriage cost.
                **(
                    {"carried_pack_kg": round(a.pack_weight_kg, 1)}
                    if a.pack_weight_kg is not None
                    else {}
                ),
                "note": (
                    "activity already performed (past load, not a constraint "
                    "to schedule around): if `regions` overlaps today's "
                    "planned work and it was logged in the last 1-2 days at "
                    "'moderate'/'hard' intensity, that region may still be "
                    "recovering — lighten volume/intensity there or "
                    "prioritize a different region instead of stacking on "
                    "top. A `carried_pack_kg` entry means this was a loaded "
                    "carry (weighted walk/run/hike) — weigh its fatigue cost "
                    "above what `intensity` alone implies, especially for "
                    "legs/core."
                ),
            }
            for a in obj_ctx.recent_activities
        ]
    if obj_ctx.ailments:
        block["ailments"] = [
            {
                "label": a.label,
                "onset_date": a.onset_date.isoformat(),
                "status": a.status,
                "notes": a.notes,
                "latest_severity": a.latest_severity,
                "latest_check_in_date": a.latest_check_in_date.isoformat()
                if a.latest_check_in_date
                else None,
                "check_ins": [
                    {
                        "date": c.check_in_date.isoformat(),
                        "severity": c.severity,
                        "note": c.note,
                    }
                    for c in a.check_ins
                ],
                "note": (
                    "date-anchored injury episode with daily severity check-ins "
                    "(0=none, 10=worst): train AROUND the latest severity and "
                    "trajectory — lighten or omit aggravating patterns when "
                    "severity is moderate/high or trending worse; NEVER "
                    "prescribe treatment/rehab (defer to PT). Static "
                    "constraints may also apply."
                ),
            }
            for a in obj_ctx.ailments
        ]
    return block


def _context_block(
    ctx: MaterializeContext,
    today: date,
    obj_ctx: CoachObjectiveContext | None = None,
) -> str:
    """Compact JSON the model is grounded on — real ids, targets, recent weights,
    and (when set) the objective + constraints to periodize toward / around."""
    templates = []
    for tpl in ctx.templates.values():
        templates.append(
            {
                "template_id": tpl.template_id,
                "name": tpl.name,
                "exercises": [
                    {
                        "exercise_id": te.exercise_id,
                        "name": te.name,
                        "is_timed": te.is_timed,
                        "target_sets": te.target_sets,
                        "target_reps": te.target_reps,
                        "target_weight": te.target_weight,
                        "last_logged_weight": te.last_weight,
                    }
                    for te in tpl.exercises
                ],
            }
        )
    payload: dict = {
        "today": today.isoformat(),
        "today_weekday": today.weekday(),  # 0=Mon
        "weight_unit": ctx.weight_unit,
        "templates": templates,
    }
    if ctx.preferred_weekdays:
        payload["preferred_weekdays"] = ctx.preferred_weekdays
    objective = _objective_block(obj_ctx, today)
    if objective is not None:
        payload["goal"] = objective
    if obj_ctx is not None and obj_ctx.candidates:
        # The exercise pool the coach may AUTHOR new routines from (real ids).
        payload["exercise_catalog"] = [
            {
                "exercise_id": c.exercise_id,
                "name": c.name,
                "is_timed": c.is_timed,
                "primary_muscles": c.primary_muscles,
                "equipment": c.equipment,
            }
            for c in obj_ctx.candidates
        ]
    return json.dumps(payload, indent=2)


def _known_template_ids(ctx: MaterializeContext) -> set[int]:
    return set(ctx.templates.keys())


def _allowed_exercise_ids(
    ctx: MaterializeContext, obj_ctx: CoachObjectiveContext | None
) -> set[int]:
    """Exercise ids the coach may use when authoring routines: every exercise in
    the user's existing routines + the objective-driven catalog candidates."""
    ids = {te.exercise_id for tpl in ctx.templates.values() for te in tpl.exercises}
    if obj_ctx is not None:
        ids |= {c.exercise_id for c in obj_ctx.candidates}
    return ids


def _validate_grounding(
    spec: ProgramSpec,
    ctx: MaterializeContext,
    obj_ctx: CoachObjectiveContext | None = None,
) -> None:
    """Reject specs that reference ids/keys the user doesn't have (triggers retry).

    The coach may either schedule an existing ``template_id`` or author a new
    routine (``new_routines`` + ``routine_key``) from real catalog exercises."""
    known_templates = _known_template_ids(ctx)
    routine_keys = {r.key for r in spec.new_routines}
    allowed_exercises = _allowed_exercise_ids(ctx, obj_ctx)
    # Validate across every block (flat spec = one block; phased = the season).
    schedule = all_schedule(spec)
    progressions = all_progressions(spec)

    if not schedule:
        raise ValueError("schedule is empty — at least one routine must be scheduled")

    # Every authored routine must have exercises drawn only from real ids.
    for r in spec.new_routines:
        if not r.exercises:
            raise ValueError(f"new routine '{r.key}' has no exercises")
        bad = {e.exercise_id for e in r.exercises} - allowed_exercises
        if bad:
            raise ValueError(
                f"routine '{r.key}' references unknown exercise_id(s): {sorted(bad)} "
                "— use only exercise_id values from templates or exercise_catalog"
            )

    # Every schedule/progression target must resolve to a known template or a
    # routine defined in this spec.
    for e in schedule:
        if e.template_id is not None and e.template_id not in known_templates:
            raise ValueError(f"schedule references unknown template_id: {e.template_id}")
        if e.routine_key is not None and e.routine_key not in routine_keys:
            raise ValueError(f"schedule references undefined routine_key: '{e.routine_key}'")
    for p in progressions:
        if p.template_id is not None and p.template_id not in known_templates:
            raise ValueError(f"progression references unknown template_id: {p.template_id}")
        if p.routine_key is not None and p.routine_key not in routine_keys:
            raise ValueError(
                f"progression references undefined routine_key: '{p.routine_key}'"
            )


def _resolve_spec():
    """The active coach ModelSpec: VIRES_COACH_LLM env → SSM (60s TTL) → default.

    The code default is the pre-adapter behavior (Anthropic + coach_model),
    so a deploy with no SSM param seeded is behavior-identical.

    OpenRouter models get a ``reasoning`` override applied here (rather than
    requiring the flip value itself to carry one): a reasoning-capable model
    (e.g. Kimi K2.6) can spend its entire output budget on invisible
    chain-of-thought and return empty content with a clean ``finish_reason
    ="stop"`` (config#1999, root-caused + fixed in krepis#16). Defaulting to
    ``{"exclude": True}`` (cheapest, longest-content option per krepis#16's
    live comparison) means the operational flip surface can stay the plain
    ``"openrouter:<model>"`` string without depending on remembering an
    inline reasoning directive. An explicit ``reasoning`` supplied via the
    SSM/env JSON form still wins.
    """
    from dataclasses import replace

    from krepis.llm_config import ModelSpec, resolve_model_spec

    settings = get_settings()
    spec = resolve_model_spec(
        settings.coach_llm_ssm_param,
        env_var="VIRES_COACH_LLM",
        default=ModelSpec(
            "anthropic", settings.coach_model, max_tokens=settings.coach_max_tokens
        ),
        max_tokens=settings.coach_max_tokens,
    )
    if spec.provider == "openrouter" and spec.reasoning is None:
        spec = replace(spec, reasoning={"exclude": True})
    return spec


def _api_key_for(spec) -> str | None:  # noqa: ANN001
    """The settings-held key for the active provider (VIRES_-prefixed env,
    SSM-hydrated at deploy — NOT the bare env vars krepis defaults to)."""
    settings = get_settings()
    if spec.provider == "anthropic":
        return settings.anthropic_api_key
    return settings.openrouter_api_key


def generate_spec(
    message: str,
    ctx: MaterializeContext,
    today: date,
    prior_spec: ProgramSpec | None = None,
    obj_ctx: CoachObjectiveContext | None = None,
) -> ProgramSpec:
    """Call the model (forced structured output) and return a validated,
    grounded ProgramSpec.

    Runs through the krepis provider-agnostic adapter: forced tool-use on the
    anthropic transport, strict json_schema on OpenAI-compatible providers —
    the same validated ``ProgramSpec`` contract either way. The grounding
    check (`_validate_grounding`) plugs into the adapter's bounded corrective
    retry, so an ungrounded spec is fed back to the model exactly as before.

    When ``obj_ctx`` carries an active objective/constraints, the model is asked
    to reverse-build the mesocycle to peak/taper to the objective's date and to
    train around the constraints (see the system prompt)."""
    # Imported lazily so the app (and its tests) load without the SDK/key present.
    from krepis.llm import LLMClient, LLMError
    from krepis.llm_config import LLMConfigError

    try:
        spec_cfg = _resolve_spec()
    except LLMConfigError as e:
        raise CoachUnavailable(f"AI coach model config is invalid: {e}") from e
    api_key = _api_key_for(spec_cfg)
    if not api_key:
        raise CoachUnavailable(
            f"AI coach is not configured (no API key for provider "
            f"'{spec_cfg.provider}')."
        )

    client = LLMClient(spec_cfg, api_key=api_key)

    user_text = (
        f"CONTEXT:\n{_context_block(ctx, today, obj_ctx)}\n\nREQUEST:\n{message.strip()}"
    )
    if prior_spec is not None:
        user_text += (
            "\n\nThis is a REFINEMENT of the existing plan below. Apply the request "
            "to it and emit the full updated spec:\n"
            f"{prior_spec.model_dump_json(indent=2)}"
        )

    def _grounding(spec: ProgramSpec) -> None:
        _validate_grounding(spec, ctx, obj_ctx)

    try:
        result = client.structured(
            system=load_system_prompt(),
            user_content=user_text,
            schema=ProgramSpec,
            schema_name=TOOL_NAME,
            validate=_grounding,
            attempts=2,  # one initial try + one correction retry (unchanged)
            max_tokens=get_settings().coach_max_tokens,
        )
    except LLMConfigError as e:
        raise CoachUnavailable(f"AI coach configuration error: {e}") from e
    except LLMError as e:
        _record_telemetry(None, spec_cfg, failed_usage=e.usage)
        raise CoachError(f"coach could not produce a valid program: {e}") from e

    _record_telemetry(result, spec_cfg)
    return result.parsed


def _record_telemetry(result, spec_cfg, *, failed_usage=None) -> None:  # noqa: ANN001
    """Cost row + SFT distillation capture for one generation (or the spend of
    a failed one).

    Best-effort by declared exception: the deliverable is the training
    program; a telemetry failure is (a) the swallowed mode, (b) the program
    still returns / the CoachError still raises, (c) recorded on a WARNING
    log line — the fail-loud policy's accepted secondary-observability shape.
    """
    from pathlib import Path

    settings = get_settings()
    try:
        import json as _json

        from krepis.cost import record_llm_call

        if result is not None:
            record = record_llm_call(result, extra_fields={"product": "vires_coach"})
        elif failed_usage is not None:
            from krepis.llm import LLMResult

            record = record_llm_call(
                LLMResult(
                    text="", model=spec_cfg.model, provider=spec_cfg.provider,
                    usage=failed_usage, raw_request={},
                ),
                extra_fields={"product": "vires_coach", "failed": True},
            )
        else:
            return
        log_path = Path(settings.coach_cost_log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a") as fh:
            fh.write(_json.dumps(record, default=str) + "\n")
        logger.info(
            "coach cost: $%.5f (%s %s, in=%d out=%d, source=%s)",
            record["cost_usd"], record["provider"], record["model"],
            record["input_tokens"], record["output_tokens"], record["cost_source"],
        )
    except Exception as e:  # noqa: BLE001 — telemetry never breaks the coach
        logger.warning("coach cost telemetry skipped: %s", e)

    if result is None:
        return
    try:
        from krepis.llm_capture import capture_llm_call

        capture_llm_call(
            result,
            producer="vires_coach",
            sink_path=settings.coach_sft_sink_path,
            meta={"provider": spec_cfg.provider},
        )
    except Exception as e:  # noqa: BLE001 — telemetry never breaks the coach
        logger.warning("coach SFT capture skipped: %s", e)
