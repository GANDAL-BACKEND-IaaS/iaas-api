from collections.abc import Callable
from datetime import timedelta
from functools import lru_cache

from app.application.ports.iam import GlobalRole, IamPort, Identity
from app.core.settings import get_settings
from app.core.tokens import decode_token
from app.infrastructure.iam.fake_iam import FakeIamClient
from app.shared.seed.loader import load_rights_catalog


@lru_cache
def get_token_decoder() -> Callable[[str], Identity]:
    """Valide localement les jetons émis par l'IAM, sans le rappeler."""
    secret = get_settings().iam_jwt_secret
    return lambda token: decode_token(token, secret)


@lru_cache
def get_iam() -> IamPort:
    """Point unique de branchement : on remplacera le mock par le vrai client IAM ici."""
    settings = get_settings()
    client = FakeIamClient(
        secret=settings.iam_jwt_secret,
        token_ttl=timedelta(seconds=settings.iam_token_ttl_seconds),
        known_rights=load_rights_catalog().right_codes,
    )
    if settings.iam_seed_demo_users:
        client.add_user("admin@iaas.cm", "admin123", "Admin", "Root", GlobalRole.ADMIN)
        client.add_user("alice@iaas.cm", "alice123", "Alice", "Ngono")
        client.add_user("bob@iaas.cm", "bob123", "Bob", "Mbarga")
    return client