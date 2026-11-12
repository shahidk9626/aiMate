"""Request and response models for the business profile and team."""

import re
import uuid
from datetime import datetime
from typing import Annotated, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, model_validator

from app.modules.identity.schemas import Name, Timezone
from app.modules.tenancy.models import MembershipStatus, Role, TenantStatus

# BCP 47 subset we support: language, optional region ("en", "en-IN", "hi-IN").
_LOCALE = re.compile(r"^[a-z]{2,3}(-[A-Z]{2})?$")


def _locale(value: str) -> str:
    if not _LOCALE.fullmatch(value):
        raise ValueError("Use a locale such as en, en-IN or en-GB.")
    return value


class TenantOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    timezone: str
    locale: str
    status: TenantStatus
    created_at: datetime


class UpdateTenantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name | None = None
    timezone: Timezone | None = None
    locale: Annotated[str, AfterValidator(_locale)] | None = None

    @model_validator(mode="after")
    def _at_least_one(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("Provide at least one field to change.")
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null.")
        return self


class MemberOut(BaseModel):
    user_id: uuid.UUID
    full_name: str
    email: str
    role: Role
    status: MembershipStatus
    joined_at: datetime


class UpdateMemberRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Role
