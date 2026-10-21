import pytest
from agrovision.config import Settings
from pydantic import ValidationError


def production_settings(**kwargs):
    return Settings(
        _env_file=None,
        environment="production",
        download_secret="x" * 32,
        dev_token_secret="",
        oidc_issuer="https://identity.example",
        oidc_jwks_url="https://identity.example/jwks",
        **kwargs,
    )


def test_empty_optional_research_path_does_not_enable_research():
    assert production_settings(research_bundle_dir="").research_bundle_dir is None


def test_nonempty_research_path_still_refused_in_production():
    with pytest.raises(ValidationError, match="Production refuses"):
        production_settings(research_bundle_dir="artifacts/research")
