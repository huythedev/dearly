"""Request schemas and domain input validation."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from localization import RequestError
from pydantic import BaseModel, ConfigDict, Field

from .constants import LEGACY_SUPPORT, SUPPORT


def fail(message: str, status: int = 400, **parameters):
    raise RequestError(message, status, **parameters)


def support_field(payload: dict) -> str:
    value = text_field(payload, "support", 80, default="listen")
    value = LEGACY_SUPPORT.get(value, value)
    if value not in SUPPORT:
        fail("Invalid support preference.")
    return value


def identifier(value) -> str:
    try:
        return str(uuid.UUID(str(value))).upper()
    except (ValueError, TypeError, AttributeError):
        fail("Invalid ID.")


def new_id() -> str:
    return str(uuid.uuid4()).upper()


def text_field(
    payload: dict, key: str, maximum: int, *, default=None, empty=False
) -> str:
    value = payload.get(key, default)
    if not isinstance(value, str):
        fail("Missing or invalid field {field}.", field=key)
    value = value.strip()
    if (not value and not empty) or len(value) > maximum:
        fail(
            "{field}: use between {minimum} and {maximum} characters.",
            field=key,
            minimum=0 if empty else 1,
            maximum=maximum,
        )
    return value


def bool_field(payload, key, default=False):
    value = payload.get(key, default)
    if not isinstance(value, bool):
        fail("{field} must be true/false.", field=key)
    return value


def age_on(birth_date: str, today: date) -> int:
    born = date.fromisoformat(birth_date)
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def validate_birth(value: str, now: float) -> str:
    try:
        born = date.fromisoformat(value)
        age = age_on(born.isoformat(), datetime.fromtimestamp(now, timezone.utc).date())
    except (TypeError, ValueError):
        fail("Invalid date of birth.")
    if not 16 <= age <= 100:
        fail("Accounts are available for ages 16 through 100.")
    return born.isoformat()


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=10, max_length=128)


class Registration(Credentials):
    nickname: str = Field(min_length=1, max_length=40)
    birthDate: str = Field(min_length=10, max_length=10)


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requestID: str = Field(min_length=36, max_length=36)
    kind: str = Field(max_length=40)
    payload: dict = Field(default_factory=dict)
