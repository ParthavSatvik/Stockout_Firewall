from pydantic import BaseModel, EmailStr, Field

from app.models.core import UserRole


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str
    role: UserRole
    business_name: str
    city: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


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

    model_config = {"from_attributes": True}
