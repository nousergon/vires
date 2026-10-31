"""Optional-key convergence in deploy-on-merge.sh (vires-ops#82, PROD-06).

The old hydration blocks only ever WROTE a key: when the SSM parameter was gone
they logged and left whatever an earlier deploy had put in ``.env``, so deleting
the parameter revoked nothing. ``infrastructure/lib/optional_ssm_env.sh`` makes
it three-state, and these tests drive the real shell functions against a stub
``aws`` on PATH (no AWS, no network):

* present parameter            -> key written
* CONFIRMED ParameterNotFound  -> key removed (revoked)
* AccessDenied / network / ""  -> unknown, ``.env`` left exactly as it was

The end-to-end cases start from an already-hydrated, already-cached key and
follow it through source deletion, deploy convergence, a restart (fresh
Settings) and the route refusing with 503 before any outbound request.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
LIB = REPO / "infrastructure" / "lib" / "optional_ssm_env.sh"
DEPLOY = REPO / "infrastructure" / "deploy-on-merge.sh"

STT = "/vires/stt_api_key"
VAPID_PUB = "/vires/vapid_public_key"
VAPID_PRIV = "/vires/vapid_private_key"

# Stub `aws`: behaviour per parameter comes from $STUB_DIR/<name with / -> _>.
# First line is the mode; for `value`, the remaining lines are the value.
_STUB_AWS = r"""#!/bin/bash
name=""
while [ $# -gt 0 ]; do
  if [ "$1" = "--name" ]; then name="$2"; fi
  shift
done
echo "$name" >> "$STUB_DIR/calls"
f="$STUB_DIR/$(printf '%s' "$name" | tr '/' '_')"
mode=$(head -n1 "$f" 2>/dev/null || echo notfound)
case "$mode" in
  value)    tail -n +2 "$f"; exit 0 ;;
  none)     echo "None"; exit 0 ;;
  notfound) echo "An error occurred (ParameterNotFound) when calling GetParameter" >&2
            exit 254 ;;
  denied)   echo "An error occurred (AccessDeniedException) when calling GetParameter" >&2
            exit 254 ;;
  network)  echo 'Could not connect to the endpoint URL: "https://ssm.amazonaws.com/"' >&2
            exit 255 ;;
  *)        echo "stub: unknown mode $mode" >&2; exit 2 ;;
esac
"""


@pytest.fixture
def box(tmp_path):
    """A fake box: stub aws on PATH, an empty .env, and a param-mode setter."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    aws = bindir / "aws"
    aws.write_text(_STUB_AWS)
    aws.chmod(0o755)
    stub = tmp_path / "stub"
    stub.mkdir()
    env_file = tmp_path / ".env"
    env_file.write_text("")

    class Box:
        env = env_file

        @staticmethod
        def param(name: str, mode: str, value: str = "") -> None:
            body = mode + ("\n" + value if mode == "value" else "") + "\n"
            (stub / name.replace("/", "_")).write_text(body)

        @staticmethod
        def run(snippet: str) -> subprocess.CompletedProcess:
            script = f'set -uo pipefail\nENV_FILE="{env_file}"\n. "{LIB}"\n{snippet}\n'
            return subprocess.run(
                ["bash", "-c", script],
                env={**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}", "STUB_DIR": str(stub)},
                capture_output=True,
                text=True,
                check=True,
            )

        @staticmethod
        def lines() -> list[str]:
            return env_file.read_text().splitlines()

    return Box


def _stt(box) -> subprocess.CompletedProcess:
    return box.run(f"hydrate_optional_key {STT} VIRES_STT_API_KEY stt")


def _vapid(box) -> subprocess.CompletedProcess:
    return box.run(
        f"hydrate_optional_pair {VAPID_PUB} VIRES_VAPID_PUBLIC_KEY '' "
        f"{VAPID_PRIV} VIRES_VAPID_PRIVATE_KEY --with-decryption push"
    )


# --- single key ------------------------------------------------------------ #


def test_present_key_is_written_and_replaces_old(box):
    box.env.write_text("OTHER=1\nVIRES_STT_API_KEY=old\n")
    box.param(STT, "value", "new-key")
    out = _stt(box)
    assert box.lines() == ["OTHER=1", "VIRES_STT_API_KEY=new-key"]
    assert "new-key" not in out.stdout + out.stderr  # value never echoed


def test_confirmed_not_found_clears_already_hydrated_key(box):
    box.env.write_text("OTHER=1\nVIRES_STT_API_KEY=stale\n")
    box.param(STT, "notfound")
    out = _stt(box)
    assert box.lines() == ["OTHER=1"]
    assert "revoked" in out.stdout


def test_confirmed_not_found_with_no_key_is_a_quiet_noop(box):
    box.env.write_text("OTHER=1\n")
    box.param(STT, "notfound")
    out = _stt(box)
    assert box.lines() == ["OTHER=1"]
    assert "feature unavailable" in out.stdout


@pytest.mark.parametrize("mode", ["denied", "network", "none"])
def test_unknown_outcomes_leave_env_untouched(box, mode):
    before = "OTHER=1\nVIRES_STT_API_KEY=keep-me\n"
    box.env.write_text(before)
    box.param(STT, mode)
    out = _stt(box)
    assert box.env.read_text() == before
    assert "left unchanged" in out.stdout


def test_env_file_stays_owner_only(box):
    box.param(STT, "value", "k")
    _stt(box)
    assert box.env.stat().st_mode & 0o777 == 0o600


# --- VAPID keypair --------------------------------------------------------- #


def test_vapid_pair_written_when_both_present(box):
    box.param(VAPID_PUB, "value", "pub")
    box.param(VAPID_PRIV, "value", "priv")
    _vapid(box)
    assert box.lines() == ["VIRES_VAPID_PUBLIC_KEY=pub", "VIRES_VAPID_PRIVATE_KEY=priv"]


@pytest.mark.parametrize("missing", [VAPID_PUB, VAPID_PRIV])
def test_vapid_pair_cleared_when_either_confirmed_absent(box, missing):
    box.env.write_text("VIRES_VAPID_PUBLIC_KEY=pub\nVIRES_VAPID_PRIVATE_KEY=priv\nOTHER=1\n")
    box.param(VAPID_PUB, "value", "pub")
    box.param(VAPID_PRIV, "value", "priv")
    box.param(missing, "notfound")
    _vapid(box)
    assert box.lines() == ["OTHER=1"]


@pytest.mark.parametrize("mode", ["denied", "network"])
def test_vapid_pair_untouched_on_unknown(box, mode):
    before = "VIRES_VAPID_PUBLIC_KEY=pub\nVIRES_VAPID_PRIVATE_KEY=priv\n"
    box.env.write_text(before)
    box.param(VAPID_PUB, "value", "pub")
    box.param(VAPID_PRIV, mode)
    _vapid(box)
    assert box.env.read_text() == before


# --- deploy script wiring --------------------------------------------------- #


def test_deploy_script_uses_the_convergent_helpers():
    src = DEPLOY.read_text()
    assert "infrastructure/lib/optional_ssm_env.sh" in src
    assert "hydrate_optional_key" in src and "VIRES_STT_API_KEY" in src
    assert "hydrate_optional_pair" in src and "VIRES_VAPID_PRIVATE_KEY" in src
    # The write-only pattern this replaced must not come back.
    assert 'get-parameter --name "$STT_PARAM"' not in src
    # Retired magic-link key: scrubbed, never hydrated.
    assert "env_clear VIRES_RESEND_API_KEY" in src
    assert "resend_api_key" not in src


def test_deploy_script_parses():
    subprocess.run(["bash", "-n", str(DEPLOY)], check=True)
    subprocess.run(["bash", "-n", str(LIB)], check=True)


# --- end to end: hydrated + cached key -> delete -> converge -> 503 -------- #


class _NoOutbound:
    """Stands in for httpx.AsyncClient in api.services.stt; any use is a failure."""

    constructed = 0

    def __init__(self, *a, **kw):
        type(self).constructed += 1
        raise AssertionError("transcription made an outbound request")


def _restart_settings(env_file: Path, monkeypatch):
    """What `systemctl restart vires` does to config: a fresh Settings from .env."""
    from api.config import Settings, get_settings

    monkeypatch.delenv("VIRES_STT_API_KEY", raising=False)
    fresh = Settings(_env_file=str(env_file))
    monkeypatch.setattr(get_settings(), "stt_api_key", fresh.stt_api_key)
    return fresh


def _post_audio(client):
    return client.post(
        "/app/api/coach/transcribe", content=b"audio", headers={"content-type": "audio/webm"}
    )


def test_deleted_key_converges_to_503_with_no_outbound_call(box, client, monkeypatch):
    # 1. An earlier deploy hydrated the key and the running process cached it.
    box.env.write_text("VIRES_STT_API_KEY=hydrated-earlier\n")
    assert _restart_settings(box.env, monkeypatch).stt_api_key == "hydrated-earlier"

    # 2. The SSM parameter is deleted; the old code left the cached key serving.
    box.param(STT, "notfound")

    # 3. The next deploy converges .env, then restarts the service.
    _stt(box)
    assert "VIRES_STT_API_KEY" not in box.env.read_text()
    assert _restart_settings(box.env, monkeypatch).stt_api_key is None

    # 4. The route refuses before any provider egress.
    _NoOutbound.constructed = 0
    monkeypatch.setattr("api.services.stt.httpx.AsyncClient", _NoOutbound)
    resp = _post_audio(client)
    assert resp.status_code == 503
    assert _NoOutbound.constructed == 0


def test_access_denied_keeps_voice_input_serving(box, client, monkeypatch):
    # A transient/permission failure must never be read as revocation.
    box.env.write_text("VIRES_STT_API_KEY=hydrated-earlier\n")
    box.param(STT, "denied")
    _stt(box)
    assert _restart_settings(box.env, monkeypatch).stt_api_key == "hydrated-earlier"

    async def fake(audio: bytes, content_type: str) -> str:
        return "ok"

    monkeypatch.setattr("api.routers.coach.transcribe_audio", fake)
    assert _post_audio(client).status_code == 200


def test_transcribe_503_without_key_makes_no_outbound_call(client, monkeypatch):
    from api.config import get_settings

    monkeypatch.setattr(get_settings(), "stt_api_key", None)
    _NoOutbound.constructed = 0
    monkeypatch.setattr("api.services.stt.httpx.AsyncClient", _NoOutbound)
    resp = _post_audio(client)
    assert resp.status_code == 503
    assert _NoOutbound.constructed == 0
