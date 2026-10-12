from pydantic import BaseModel, Field

from app.application.ports.iam import AuthToken, GlobalRole, Identity


class LoginIn(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=1)


class UserUpdateIn(BaseModel):
    """Champs absents ou null = inchangés."""
    email: str | None = Field(default=None, min_length=3)
    first_name: str | None = Field(default=None, min_length=1)
    last_name: str | None = Field(default=None, min_length=1)


class PasswordChangeIn(BaseModel):
    old_password: str = Field(min_length=1)
    new_password: str = Field(min_length=6)


class TokenOut(BaseModel):
    access_token: str
    token_type: str
    expires_in: int

    @classmethod
    def of(cls, token: AuthToken) -> "TokenOut":
        return cls(access_token=token.access_token, token_type=token.token_type,
                   expires_in=token.expires_in)


class IdentityOut(BaseModel):
    user_id: str
    email: str
    first_name: str
    last_name: str
    role: GlobalRole

    @classmethod
    def of(cls, identity: Identity) -> "IdentityOut":
        return cls(user_id=identity.user_id, email=identity.email,
                   first_name=identity.first_name, last_name=identity.last_name,
                   role=identity.role)