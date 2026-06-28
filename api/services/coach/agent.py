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
from datetime import date

from pydantic import ValidationError

from api.config import get_settings
from api.schemas.coach import ProgramSpec
from api.services.coach.materialize import MaterializeContext

TOOL_NAME = "emit_program_spec"

SYSTEM_PROMPT = """\
You are an expert strength & conditioning coach building a multi-week training \
program for a single athlete. Convert their request into a structured program by \
calling the emit_program_spec tool — this is the ONLY way to respond.

Hard rules:
- Reference ONLY the template_id and exercise_id values given in CONTEXT. Never \
invent ids or exercises.
- Express progression as CURVES (start/end values + mode), NOT per-week numbers — \
the system materializes the weekly sets/reps/weight deterministically. A typical \
strength block ramps reps DOWN (e.g. 10 -> 4) while weight ramps UP; use a \
'percent_of_start' weight curve (e.g. 1.0 -> 1.3 for +30%) unless the user gives \
absolute weights.
- weekday is 0=Monday … 6=Sunday. One schedule entry = that template once per week \
on that weekday. "each routine once a week" = one entry per template.
- Pick a sensible start_date (default: the provided today, or the next occurrence of \
the requested day). Set deload_weeks only if the user asks or the block is long.
- Write a concise, friendly coach_summary explaining the plan in plain English \
(weeks, frequency, how reps/weight move, any deload).
- Respect the athlete's weight unit given in CONTEXT.
"""


class CoachUnavailable(RuntimeError):
    """Raised when the coach can't run (no API key). Router maps this to HTTP 503."""


class CoachError(RuntimeError):
    """The model failed to produce a usable spec after retry."""


def _context_block(ctx: MaterializeContext, today: date) -> str:
    """Compact JSON the model is grounded on — real ids, targets, recent weights."""
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
    return json.dumps(
        {
            "today": today.isoformat(),
            "today_weekday": today.weekday(),  # 0=Mon
            "weight_unit": ctx.weight_unit,
            "templates": templates,
        },
        indent=2,
    )


def _known_template_ids(ctx: MaterializeContext) -> set[int]:
    return set(ctx.templates.keys())


def _validate_grounding(spec: ProgramSpec, ctx: MaterializeContext) -> None:
    """Reject specs that reference templates the user doesn't have (triggers retry)."""
    known = _known_template_ids(ctx)
    referenced = {e.template_id for e in spec.schedule}
    unknown = referenced - known
    if unknown:
        raise ValueError(f"schedule references unknown template_id(s): {sorted(unknown)}")
    if not spec.schedule:
        raise ValueError("schedule is empty — at least one template must be scheduled")


def generate_spec(
    message: str,
    ctx: MaterializeContext,
    today: date,
    prior_spec: ProgramSpec | None = None,
) -> ProgramSpec:
    """Call the model (forced tool-use) and return a validated, grounded ProgramSpec."""
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise CoachUnavailable("AI coach is not configured (no Anthropic API key).")

    # Imported lazily so the app (and its tests) load without the SDK/key present.
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    tool = {
        "name": TOOL_NAME,
        "description": "Emit the structured multi-week training program.",
        "input_schema": ProgramSpec.model_json_schema(),
    }

    user_text = f"CONTEXT:\n{_context_block(ctx, today)}\n\nREQUEST:\n{message.strip()}"
    if prior_spec is not None:
        user_text += (
            "\n\nThis is a REFINEMENT of the existing plan below. Apply the request "
            "to it and emit the full updated spec:\n"
            f"{prior_spec.model_dump_json(indent=2)}"
        )
    messages: list[dict] = [{"role": "user", "content": user_text}]

    last_err: Exception | None = None
    for _attempt in range(2):  # one initial try + one correction retry
        resp = client.messages.create(
            model=settings.coach_model,
            max_tokens=settings.coach_max_tokens,
            system=SYSTEM_PROMPT,
            tools=[tool],
            tool_choice={"type": "tool", "name": TOOL_NAME},
            messages=messages,
        )
        tool_input = _extract_tool_input(resp)
        if tool_input is None:
            last_err = CoachError("model did not call emit_program_spec")
            break
        try:
            spec = ProgramSpec.model_validate(tool_input)
            _validate_grounding(spec, ctx)
            return spec
        except (ValidationError, ValueError) as e:
            last_err = e
            # Feed the error back and ask for a corrected spec (forced tool again).
            messages.append({"role": "assistant", "content": resp.content})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"That emit_program_spec call was invalid: {e}\n"
                        "Emit a corrected emit_program_spec using only the CONTEXT ids."
                    ),
                }
            )

    raise CoachError(f"coach could not produce a valid program: {last_err}")


def _extract_tool_input(resp) -> dict | None:  # noqa: ANN001
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use" and block.name == TOOL_NAME:
            return block.input
    return None
