from datetime import datetime
from typing import Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
)


class UserCreate(BaseModel):
    username: str = Field(
        min_length=3,
        max_length=20,
    )
    email: EmailStr
    password: str = Field(
        min_length=6,
        max_length=128,
    )
    csrf_token: str


class UserLogin(BaseModel):
    username: str = Field(
        min_length=1,
        max_length=20,
    )
    password: str = Field(
        min_length=1,
        max_length=128,
    )
    csrf_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(
        min_length=1,
        max_length=200,
    )
    new_password: str = Field(
        min_length=8,
        max_length=128,
    )


class UserProfileRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    gender: Optional[str] = None
    age: Optional[int] = None
    weight: Optional[float] = None
    height: Optional[float] = None
    target: Optional[str] = None


class UserRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    id: int
    username: str
    email: EmailStr
    is_active: bool
    created_at: datetime
    profile: Optional[UserProfileRead] = None


class PurchaseRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    id: int
    plan_id: str
    status: str
    amount_cents: Optional[int] = None
    currency: Optional[str] = None
    created_at: datetime


class GeneratedPlanRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    id: int
    plan_id: str
    content: str
    created_at: datetime
    updated_at: datetime