from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator
from app.core.permissions import Role

PROFILE_MODULES = {
    "retail": ["products", "customers", "orders", "inventory", "marketing", "suppliers", "finance"],
    "restaurant": ["menu", "orders", "branches", "ingredients", "inventory", "suppliers", "finance"],
    "manufacturing": ["materials", "products", "production", "inventory", "suppliers", "finance"],
    "services": ["clients", "projects", "employees", "hours", "invoices", "finance"],
    "wholesale": ["products", "customers", "orders", "inventory", "suppliers", "purchasing", "finance"],
}


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Credentials(Input):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: Annotated[str, StringConstraints(strip_whitespace=False, min_length=12, max_length=128)]

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()

    # Password whitespace is significant; override the model's general string trimming.
    @field_validator("password", mode="before")
    @classmethod
    def password_string(cls, value):
        if not isinstance(value, str):
            raise ValueError("Password must be a string")
        return value


class Register(Credentials):
    name: str = Field(min_length=1, max_length=100)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    email: str
    name: str
    is_platform_admin: bool


class SessionOut(BaseModel):
    user: UserOut
    csrf_token: str
    expires_at: datetime


class BusinessInput(Input):
    name: str = Field(min_length=1, max_length=100)
    business_type: Literal["retail", "restaurant", "manufacturing", "services", "wholesale"]
    country: str = Field(pattern=r"^[A-Z]{2}$")
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    timezone: str = Field(min_length=1, max_length=80)
    reporting_month: int = Field(default=1, ge=1, le=12)
    modules: list[str] | None = None

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Use an IANA timezone")
        return value

    @model_validator(mode="after")
    def valid_modules(self):
        allowed = PROFILE_MODULES[self.business_type]
        if self.modules is None:
            self.modules = allowed.copy()
        if not self.modules or len(self.modules) != len(set(self.modules)) or not set(self.modules) <= set(allowed):
            raise ValueError("Select unique modules supported by this business profile")
        return self


class BusinessOut(BusinessInput):
    id: UUID
    role: Role
    permissions: list[str]
    created_at: datetime
    updated_at: datetime
    data_status: Literal["empty", "has_data"] = "empty"


class MemberInput(Input):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    role: Role


class RoleInput(Input):
    role: Role


class MemberOut(BaseModel):
    user_id: UUID
    name: str
    email: str
    role: Role


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    event: str
    user_id: UUID | None
    target_id: str | None
    created_at: datetime
