"""The coach LLM call: grounded, forced structured output.

A single krepis ``structured()`` call with a **forced** tool choice / strict
json_schema makes the model emit a ``ProgramSpec`` (validated by Pydantic)
rather than free text we'd have to parse — the institutional pattern
(structured tool-use over ``json.loads``). The model is *grounded*: it only
ever sees, and may only reference, the user's real template/exercise ids. It
proposes a declarative spec (schedule + curves); the deterministic
materializer does the arithmetic.

Routing (2026-08-29 migration, vires-ops-I<N>): every call funnels through
the krepis router — mirrors ``flow_doctor.core.router.resolve_router_edge``
and ``metron_ext.advisor.llm`` (the fleet's two reference patterns for this
class; see ``model-router-policy.md`` §5). Direct-Anthropic is retired fleet-
wide by Brian's 2026-08-29 ruling ("we shouldn't be using the anthropic api
at all") — the prior code default (``ModelSpec("anthropic", ...)``) and the
narrower ``_reject_direct_openrouter`` guard from alpha-engine-config-I9092
are both superseded by :func:`_default_spec` (router-group-derived, fail-
closed off any non-compelled route) and :func:`_reject_non_router_override`
(an operator override may only pin the model the router edge itself serves,
never address a provider directly).
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

# Join key for cost attribution and SFT capture — registered as `vires-coach`
# in alpha-engine-config's LLM_CALLSITE_REGISTRY.yaml. krepis >=0.32 requires
# a non-empty callsite_id on every LLMClient; this call site is the one place
# the coach constructs a client.
CALLSITE_ID = "vires-coach"

# krepis router model_group this call site asks for — a CAPABILITY TIER, never
# a model id or provider (principle 8, substitutability). Matches the
# LLM_CALLSITE_REGISTRY.yaml `model_group: low` row already on file for
# `vires-coach`; that row's `provider`/`model` fields still name the retired
# `anthropic`/`claude-haiku-4-5` default and need an alpha-engine-config
# update to match (out of scope for this repo — flagged, not edited here).
ROUTER_GROUP = "low"

# The system prompt is loaded at call time — tuned-private if hydrated onto the
# box, else the committed public baseline (see prompt_loader). The prompt is the
# Vires coaching edge, so its tuned form is NOT in this public repo.


class CoachUnavailable(RuntimeError):
    """Raised when the coach can't run (router unresolvable or model config
    invalid). Router maps this to HTTP 503."""


class CoachRouterUnresolvable(RuntimeError):
    """The krepis router could not resolve ``ROUTER_GROUP`` to a callable
    endpoint on a compelled route.

    A distinct type (mirrors ``flow_doctor.core.router.RouterUnresolvable``
    and ``model-router-policy`` R20) so callers never mistake "the router
    could not be reached" for "the router was reached and declined" — this
    always means the LLM call did not happen at all. Caught and re-raised as
    :class:`CoachUnavailable` at the one call site that constructs a client,
    so the HTTP layer keeps its single 503 mapping.
    """


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


_COMPELLED_ROUTES = frozenset({"litellm_proxy", "egress_proxy"})


def _default_spec():
    """Router-derived default: ``resolve_group_spec(ROUTER_GROUP)``, fail-
    closed off any route that is not one of the two ``_COMPELLED_ROUTES``
    paths — ``litellm_proxy`` (the authenticated router edge) or
    ``egress_proxy`` (its registry-derived, DLP-scanned degraded fallback).

    Mirrors ``flow_doctor.core.router.resolve_router_edge`` /
    ``COMPELLED_ROUTES`` and ``model-router-policy.md`` §5 — the fleet's
    reference pattern for this class. Never falls back to a direct provider
    chosen by krepis's own internal fallback, and never constructs a bare
    ``ModelSpec("anthropic", ...)`` — the pre-adapter default this supersedes
    (Brian ruling 2026-08-29: direct Anthropic API retired fleet-wide,
    "we shouldn't be using the anthropic api at all"; "the entire nous ergon
    system should now be running through the krepis router ... no other
    parallel setups").
    """
    from krepis.router import resolve_group_spec

    settings = get_settings()
    try:
        spec, route = resolve_group_spec(ROUTER_GROUP, max_tokens=settings.coach_max_tokens)
    except Exception as exc:  # noqa: BLE001 — categorized by the raise below
        raise CoachRouterUnresolvable(
            f"router group {ROUTER_GROUP!r} did not resolve: {exc}"
        ) from exc
    resolved_route = route.get("route") if isinstance(route, dict) else None
    if resolved_route not in _COMPELLED_ROUTES:
        raise CoachRouterUnresolvable(
            f"router group {ROUTER_GROUP!r} resolved to route {resolved_route!r} "
            f"(provider={getattr(spec, 'provider', None)!r}), which is not a "
            f"compelled path — refusing a direct-provider call chosen by "
            f"krepis's own fallback (model-router-policy.md §5). Compelled "
            f"routes: {sorted(_COMPELLED_ROUTES)}"
        )
    return spec


def _reject_non_router_override(spec, source: str) -> None:  # noqa: ANN001
    """An operator override (``VIRES_COACH_LLM`` env / ``/vires/llm/coach``
    SSM) may only PIN which model the router edge itself serves — never
    bypass the edge to address a provider directly.

    An override's ``ModelSpec`` carries no ``route`` (it did not come from
    ``resolve_group_spec``), so provider identity is the only signal
    available; only ``ROUTER_EDGE_PROVIDER`` ("litellm_proxy") is verifiably
    compelled from that signal alone — a bare ``"anthropic:..."`` or
    ``"openrouter:..."`` value would construct an ``LLMClient`` that talks to
    that provider's endpoint directly, exactly the parallel setup Brian's
    2026-08-29 ruling forbids ("no other parallel setups ... it should all
    funnel through the krepis router").

    Supersedes the narrower ``_reject_direct_openrouter`` this replaced
    (alpha-engine-config-I9092 / #6367 are subsumed: neither ``openrouter``
    nor ``anthropic`` may be named directly here any more, only the edge).
    Raising rather than silently rerouting is deliberate — fail-loud, per the
    repo's rules: an operator who set that value wanted a specific model, and
    quietly serving a different one is worse than a loud 503.
    """
    from krepis.llm_config import ROUTER_EDGE_PROVIDER

    if getattr(spec, "provider", None) != ROUTER_EDGE_PROVIDER:
        raise CoachUnavailable(
            f"AI coach model config refused: {source} names provider "
            f"{getattr(spec, 'provider', None)!r} directly. Per Brian's "
            f"2026-08-29 ruling, every LLM call funnels through the krepis "
            f"router — an override may only pin the model the router edge "
            f"itself serves (provider: {ROUTER_EDGE_PROVIDER!r}), never "
            f"address a provider directly. Clear the override to use the "
            f"router-derived {ROUTER_GROUP!r} group default, or set an "
            f"explicit {ROUTER_EDGE_PROVIDER}:<model> spec."
        )


def _resolve_spec():
    """The active coach ModelSpec: ``VIRES_COACH_LLM`` env → SSM (60s TTL) →
    the router-derived default (:func:`_default_spec`).

    An env/SSM override is validated by :func:`_reject_non_router_override`
    before use; the default is already validated by :func:`_default_spec`
    (identity-compared here so the stricter override check is never applied
    to a spec that already passed the router's own compelled-route check).
    An env override is checked directly (rather than always resolving the
    router default first, only to discard it) so a set ``VIRES_COACH_LLM``
    never pays for — or depends on the availability of — a live router
    resolution it doesn't need; :func:`resolve_model_spec` applies the same
    env-first precedence internally, this only avoids the redundant work.
    """
    import os

    from krepis.llm_config import resolve_model_spec

    settings = get_settings()
    source = f"VIRES_COACH_LLM / {settings.coach_llm_ssm_param}"
    if os.environ.get("VIRES_COACH_LLM"):
        spec = resolve_model_spec(settings.coach_llm_ssm_param, env_var="VIRES_COACH_LLM")
        _reject_non_router_override(spec, source)
        return spec

    default_spec = _default_spec()
    spec = resolve_model_spec(
        settings.coach_llm_ssm_param,
        env_var="VIRES_COACH_LLM",
        default=default_spec,
    )
    if spec is not default_spec:
        _reject_non_router_override(spec, source)
    return spec


# Test seam (mirrors ``metron_ext.advisor.llm._transport_client_factory``):
# when set, its return value is injected as the transport client for every
# generation — tests patch this instead of reaching into krepis or the
# retired ``anthropic`` SDK.
_transport_client_factory = None


def generate_spec(
    message: str,
    ctx: MaterializeContext,
    today: date,
    prior_spec: ProgramSpec | None = None,
    obj_ctx: CoachObjectiveContext | None = None,
) -> ProgramSpec:
    """Call the model (forced structured output) and return a validated,
    grounded ProgramSpec.

    Runs through the krepis router edge — strict json_schema on the
    OpenAI-compatible transport every router-resolved spec uses (no
    call site here ever resolves the anthropic transport any more). The
    grounding check (`_validate_grounding`) plugs into the adapter's bounded corrective
    retry, so an ungrounded spec is fed back to the model exactly as before.

    When ``obj_ctx`` carries an active objective/constraints, the model is asked
    to reverse-build the mesocycle to peak/taper to the objective's date and to
    train around the constraints (see the system prompt)."""
    # Imported lazily so the app (and its tests) load without the SDK/key present.
    from krepis.llm import LLMClient, LLMError
    from krepis.llm_config import LLMConfigError

    try:
        spec_cfg = _resolve_spec()
    except (LLMConfigError, CoachRouterUnresolvable) as e:
        raise CoachUnavailable(f"AI coach model config is invalid: {e}") from e

    # The ROUTER EDGE resolves credentials on its own chain (SSM/env, not a
    # settings-held per-provider key) — see krepis.llm.LLMClient._resolve_api_key.
    # No explicit api_key is passed on the live path; the test seam below
    # injects one only to satisfy LLMClient's constructor when a fake
    # transport is in play.
    if _transport_client_factory is not None:
        fake = _transport_client_factory()
        client = LLMClient(
            spec_cfg, api_key="test", client_factory=lambda *_a: fake, callsite_id=CALLSITE_ID
        )
    else:
        client = LLMClient(spec_cfg, callsite_id=CALLSITE_ID)

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
