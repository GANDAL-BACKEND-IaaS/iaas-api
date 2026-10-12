from pydantic import BaseModel, ConfigDict, Field, field_validator


class RightOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code: str
    description: str


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: str
    rights: list[str]

    @field_validator("rights", mode="before")
    @classmethod
    def _codes(cls, v):
        return sorted(r.code if hasattr(r, "code") else r for r in v)


class ProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=255)
    rights: list[str] = []


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=255)
    rights: list[str] | None = None