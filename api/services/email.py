"""Magic-link email delivery via Resend's REST API.

Mirrors ``api.services.stt``'s pattern: a plain ``httpx`` call (no new pip
dependency — Resend has a first-party SDK but a single POST doesn't warrant
it), raising a typed error the router maps to an HTTP status.

In ``settings.env == "development"`` with no ``resend_api_key`` configured,
the magic link is logged instead of sent — local dev shouldn't need a live
inbox. This fallback is dev-only by construction (see ``send_magic_link``):
a missing key in any other env fails loud, never a silent no-op, since a
magic link that's silently swallowed in production is a real login-blocking
bug, not a degradable feature like the mic or push alerts.
"""

from __future__ import annotations

import logging

import httpx

from api.config import get_settings

log = logging.getLogger("vires.auth")


class EmailError(RuntimeError):
    """Resend returned an error (router maps to HTTP 502)."""


def _magic_link_html(link: str) -> str:
    return (
        f'<p>Tap to log in to Vires:</p>'
        f'<p><a href="{link}">{link}</a></p>'
        f"<p>This link expires in 5 minutes and works once.</p>"
    )


async def send_magic_link(email: str, link: str) -> None:
    settings = get_settings()
    if not settings.resend_api_key:
        if settings.env == "development":
            # WARNING, not info: nothing in this app configures the root
            # logger's level (Python defaults to WARNING), so an `info` call
            # here would be silently swallowed — exactly the kind of gap this
            # fallback exists to avoid.
            log.warning("DEV magic link for %s (no RESEND_API_KEY configured): %s", email, link)
            return
        raise EmailError("Email is not configured (RESEND_API_KEY missing).")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                json={
                    "from": settings.email_sender,
                    "to": [email],
                    "subject": "Log in to Vires",
                    "html": _magic_link_html(link),
                },
            )
    except httpx.HTTPError as e:
        raise EmailError(f"Resend request failed: {e}") from e
    if resp.status_code >= 300:
        raise EmailError(f"Resend {resp.status_code}: {resp.text[:200]}")
