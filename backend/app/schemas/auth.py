from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.core import UserRole


def _lower(v: str) -> str:
    return v.strip().lower()


# Lengths mirror the database columns: PostgreSQL rejects longer values with a 500.
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)
    full_name: str = Field(min_length=1, max_length=200)
    role: UserRole
    business_name: str = Field(min_length=1, max_length=200)
    city: str = Field(min_length=1, max_length=100)

    _email = field_validator("email")(_lower)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=256)

    _email = field_validator("email")(_lower)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: UserRole
    user_id: str


class CurrentUserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role: UserRole
    phone_e164: str | None = None
    whatsapp_opt_in: bool = False

    model_config = {"from_attributes": True}


class ContactUpdateRequest(BaseModel):
    # E.164: + then 8-15 digits, e.g. +919876543210
    phone_e164: str | None = Field(default=None, pattern=r"^\+[1-9]\d{7,14}$")
    whatsapp_opt_in: bool = False
