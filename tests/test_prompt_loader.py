"""Coach system-prompt loading: public baseline + private/override precedence."""

from __future__ import annotations

from api.services.coach.prompt_loader import BASELINE_PATH, load_system_prompt


def test_baseline_prompt_is_committed_and_loads():
    assert BASELINE_PATH.is_file()  # the public baseline must always ship
    load_system_prompt.cache_clear()
    text = load_system_prompt()
    assert "emit_program_spec" in text  # it's the real coach prompt
    assert len(text) > 100


def test_explicit_path_overrides_baseline(tmp_path, monkeypatch):
    from api.config import get_settings

    custom = tmp_path / "tuned.txt"
    custom.write_text("TUNED PRIVATE PROMPT", encoding="utf-8")
    monkeypatch.setattr(get_settings(), "coach_prompt_path", str(custom))
    load_system_prompt.cache_clear()
    try:
        assert load_system_prompt() == "TUNED PRIVATE PROMPT"
    finally:
        load_system_prompt.cache_clear()


def test_blank_override_falls_back_to_baseline(tmp_path, monkeypatch):
    from api.config import get_settings

    blank = tmp_path / "blank.txt"
    blank.write_text("   \n", encoding="utf-8")  # whitespace-only => skipped
    monkeypatch.setattr(get_settings(), "coach_prompt_path", str(blank))
    load_system_prompt.cache_clear()
    try:
        assert "emit_program_spec" in load_system_prompt()  # baseline used
    finally:
        load_system_prompt.cache_clear()
