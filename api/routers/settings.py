"""User settings — logging defaults + weight unit."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.db.identity import Identity, current_identity, get_or_create_settings
from api.db.models import UserSettings
from api.db.session import get_db
from api.schemas.settings import SettingsOut, SettingsUpdate

router = APIRouter(prefix="/settings", tags=["settings"])


def _out(s: UserSettings) -> SettingsOut:
    return SettingsOut(
        weight_unit=s.weight_unit,
        default_rest_seconds=s.default_rest_seconds,
        default_sets=s.default_sets,
        default_reps=s.default_reps,
        timer_sound=s.timer_sound,
        timer_vibration=s.timer_vibration,
        timer_notification=s.timer_notification,
        timer_keep_awake=s.timer_keep_awake,
        preferred_weekdays=s.preferred_weekdays,
    )


@router.get("", response_model=SettingsOut)
def get_settings_endpoint(
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> SettingsOut:
    return _out(get_or_create_settings(db, ident))


@router.put("", response_model=SettingsOut)
def update_settings(
    body: SettingsUpdate,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> SettingsOut:
    s = get_or_create_settings(db, ident)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(s, field, value)
    db.commit()
    db.refresh(s)
    return _out(s)
