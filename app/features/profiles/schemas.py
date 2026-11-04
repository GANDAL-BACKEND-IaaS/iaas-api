from pydantic import BaseModel, ConfigDict, Field, field_validator


class RightOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    description: str


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    rights: list[str]

    @field_validator("rights", mode="before")
    @classmethod
    def _codes(cls, value):
        return sorted(right.code if hasattr(right, "code") else right for right in value)


class ProfileCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=255)
    rights: list[str] = Field(default_factory=list)


class ProfileUpdateIn(BaseModel):
    """Champs absents ou null = inchanges. `rights: []` retire tous les droits."""

    name: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=255)
    rights: list[str] | None = None
