"""Pandolf load-carriage metabolic model.

Estimates the metabolic energy cost of walking under load — the physiological
basis for treating a ruck (weighted hike) as *training load* rather than just
distance. This is the differentiator: a route app knows you hiked 8 mi / 3000 ft,
but only Vires knows the pack weight, and pack weight dominates the metabolic
demand of load carriage.

Model
-----
Pandolf, Givoni & Goldman (1977), *J. Appl. Physiol.* 43(4):577-581 — the standard
US Army metabolic-rate equation for load carriage::

    M = 1.5·W + 2.0·(W + L)·(L / W)^2 + η·(W + L)·(1.5·V^2 + 0.35·V·G)

where
    M  = metabolic rate (watts)
    W  = body mass (kg)
    L  = external load / pack mass (kg)
    V  = walking speed (m/s)
    G  = grade (%), positive uphill
    η  = terrain factor (dimensionless; 1.0 = treadmill/paved)

Two guards on the raw equation:

* **Standing floor.** At low speed on level/negative grade the third term can drive
  M below the cost of merely standing under the load; M is clamped to the standing
  value (the first two terms), which is the accepted Pandolf floor.

* **Downhill.** Pandolf over-predicts on descents; the Santee et al. (2001)
  correction handles negative grades per segment. Tier 0 works from *aggregate*
  route metrics (total distance, total elevation *gain*), so it has no descent
  signal to correct against and models the effort at a single average operating
  point with grade ≥ 0. Per-segment ascent/descent integration with the Santee
  correction is a Tier 1 concern (it needs the GPS track). This is a deliberate,
  documented approximation — not a silent one.

Everything here is SI in / SI out. Unit conversion is the caller's job (done once,
at the API boundary).
"""

from __future__ import annotations

# Coarse terrain classes → Pandolf terrain factor η. Values from Pandolf (1977)
# and Soule & Goldman (1972) load-carriage terrain coefficients.
TERRAIN_FACTORS: dict[str, float] = {
    "treadmill": 1.0,  # blacktop / treadmill
    "road": 1.0,
    "trail": 1.2,  # dirt road / light trail
    "offtrail": 1.5,  # heavy brush / loose surface
    "snow": 1.7,  # soft snow (representative; varies with depth)
}
DEFAULT_TERRAIN = "trail"

# Plausible walking-speed window (m/s). Pandolf was validated ~0.7–2.0 m/s; we
# accept a slightly wider band and just clamp the extremes so a mistyped duration
# doesn't yield a wild cost.
_MIN_SPEED_MS = 0.3
_MAX_SPEED_MS = 2.5


def terrain_factor(terrain: str | None) -> float:
    """Terrain factor η for a coarse terrain class, defaulting to ``trail``."""
    key = (terrain or DEFAULT_TERRAIN).lower()
    return TERRAIN_FACTORS.get(key, TERRAIN_FACTORS[DEFAULT_TERRAIN])


def pandolf_metabolic_watts(
    bodyweight_kg: float,
    load_kg: float,
    speed_ms: float,
    grade_pct: float,
    eta: float,
) -> float:
    """Metabolic rate (watts) for walking under load, with the standing floor.

    Raises ``ValueError`` on non-positive body mass (the ``L/W`` term is undefined)
    — a caller must never reach this with an unknown bodyweight.
    """
    if bodyweight_kg <= 0:
        raise ValueError("bodyweight_kg must be > 0 for the Pandolf load term")
    load_kg = max(load_kg, 0.0)
    total = bodyweight_kg + load_kg

    # Standing cost under the load — the floor M can never fall below.
    standing = 1.5 * bodyweight_kg + 2.0 * total * (load_kg / bodyweight_kg) ** 2
    locomotion = eta * total * (1.5 * speed_ms**2 + 0.35 * speed_ms * grade_pct)
    return max(standing, standing + locomotion)


def ruck_metabolic_cost_kj(
    *,
    bodyweight_kg: float,
    pack_weight_kg: float,
    distance_m: float | None,
    elevation_gain_m: float | None,
    duration_s: int | None,
    terrain: str | None = DEFAULT_TERRAIN,
) -> float | None:
    """Total metabolic cost of a ruck (kJ) from aggregate route metrics.

    Returns ``None`` when distance or duration is missing/non-positive — the load
    number is genuinely uncomputable without speed, and the caller surfaces that
    honestly ("add distance + time to see load") rather than inventing a value.

    Average speed = distance / duration; average grade = gain / distance. Elevation
    gain is optional (a flat ruck ⇒ grade 0). Speed is clamped to a plausible band.
    """
    if not distance_m or not duration_s or distance_m <= 0 or duration_s <= 0:
        return None

    speed_ms = distance_m / duration_s
    speed_ms = min(max(speed_ms, _MIN_SPEED_MS), _MAX_SPEED_MS)

    gain = elevation_gain_m or 0.0
    grade_pct = max(0.0, (gain / distance_m) * 100.0) if distance_m > 0 else 0.0

    watts = pandolf_metabolic_watts(
        bodyweight_kg=bodyweight_kg,
        load_kg=pack_weight_kg,
        speed_ms=speed_ms,
        grade_pct=grade_pct,
        eta=terrain_factor(terrain),
    )
    # watts (J/s) × seconds ÷ 1000 → kJ
    return round(watts * duration_s / 1000.0, 1)
