"""Request and response models for authentication and the current user.

Email validation is deliberately structural (no extra dependency): it rejects
malformed input, and the verification email (step 2.5) proves the address is
real. Passwords are never stripped or echoed back in errors.
"""

import re
import uuid
import zoneinfo
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.modules.tenancy.models import Role

EMAIL_MAX_LENGTH = 254
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s.]{2,}$")
_TIMEZONES = frozenset(zoneinfo.available_timezones())


def _email(value: str) -> str:
    value = value.strip()
    if len(value) > EMAIL_MAX_LENGTH or not _EMAIL.fullmatch(value) or not value.isprintable():
        raise ValueError("Enter a valid email address.")
    return value


def _name(value: str) -> str:
    value = " ".join(value.split())  # trim and collapse inner whitespace
    if not value:
        raise ValueError("Must not be empty.")
    if not value.isprintable():
        raise ValueError("Contains invalid characters.")
    return value


def _timezone(value: str) -> str:
    if value not in _TIMEZONES:
        raise ValueError("Unknown time zone. Use an IANA name such as Asia/Kolkata.")
    return value


Email = Annotated[str, Field(max_length=EMAIL_MAX_LENGTH + 20), AfterValidator(_email)]
Name = Annotated[str, Field(max_length=200), AfterValidator(_name)]
# Upper bound only; the password policy (10-128) is checked by the service and
# reported as PASSWORD_POLICY with field details.
Password = Annotated[str, Field(min_length=1, max_length=1000)]


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SignupRequest(_Request):
    email: Email
    password: Password
    full_name: Name
    business_name: Name
    timezone: Annotated[str, AfterValidator(_timezone)] = "UTC"


class LoginRequest(_Request):
    # Not format-validated: any mismatch must look like wrong credentials.
    email: Annotated[str, Field(min_length=1, max_length=EMAIL_MAX_LENGTH + 20)]
    password: Password


class UpdateProfileRequest(_Request):
    full_name: Name


class ChangePasswordRequest(_Request):
    current_password: Password
    new_password: Password


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    email_verified: bool
    created_at: datetime


class MembershipOut(BaseModel):
    tenant_id: uuid.UUID
    tenant_name: str
    tenant_slug: str
    role: Role


class MeOut(BaseModel):
    user: UserOut
    memberships: list[MembershipOut]
