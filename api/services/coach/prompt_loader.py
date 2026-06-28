"""Load the coach system prompt — tuned-private if present, else public baseline.

The tuned coach prompt is the Vires *edge* (a Commercial-tier product), so it is
**gitignored** and hydrated onto the box from the private source (SSM / vires-ops)
at deploy time. The committed ``coach_system.example.txt`` is the competent public
baseline the open AGPL repo ships, so the coach works out of the box even without
the private prompt.

Resolution order (first non-empty wins):
1. ``settings.coach_prompt_path`` — explicit override (deploy/testing)
2. ``prompts/coach_system.txt`` — the tuned private prompt (gitignored)
3. ``prompts/coach_system.example.txt`` — the public baseline (committed)
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from api.config import get_settings

_PROMPT_DIR = Path(__file__).parent / "prompts"
TUNED_PATH = _PROMPT_DIR / "coach_system.txt"  # gitignored, private edge
BASELINE_PATH = _PROMPT_DIR / "coach_system.example.txt"  # committed baseline


@lru_cache
def load_system_prompt() -> str:
    candidates: list[Path] = []
    override = get_settings().coach_prompt_path
    if override:
        candidates.append(Path(override))
    candidates += [TUNED_PATH, BASELINE_PATH]
    for path in candidates:
        if path.is_file():
            text = path.read_text(encoding="utf-8").strip()
            if text:
                return text
    raise RuntimeError(
        f"No coach system prompt found (looked for {[str(p) for p in candidates]}). "
        "The committed coach_system.example.txt should always be present."
    )
