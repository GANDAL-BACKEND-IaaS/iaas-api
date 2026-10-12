import json
from dataclasses import dataclass
from pathlib import Path

SEED_DIR = Path(__file__).parent


@dataclass(frozen=True)
class RightDef:
    code: str
    description: str


@dataclass(frozen=True)
class ProfileDef:
    name: str
    description: str
    rights: tuple[str, ...]


@dataclass(frozen=True)
class RightsCatalog:
    rights: tuple[RightDef, ...]

    @property
    def right_codes(self) -> frozenset[str]:
        return frozenset(r.code for r in self.rights)


def load_rights_catalog(path: Path = SEED_DIR / "rights_catalog.json") -> RightsCatalog:
    data = json.loads(path.read_text(encoding="utf-8"))
    return RightsCatalog(tuple(RightDef(r["code"], r.get("description", "")) for r in data["rights"]))


def load_default_profiles(path: Path = SEED_DIR / "default_profiles.json") -> tuple[ProfileDef, ...]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return tuple(ProfileDef(p["name"], p.get("description", ""), tuple(p["rights"])) for p in data)