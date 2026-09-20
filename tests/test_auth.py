"""Auth: password rules, self-register group stripping, unique username → ValueError."""
import pytest

from backend.l14_security.auth import (
    User,
    create_user,
    default_mode,
    mint,
    validate_password,
)


def test_validate_password_min_len():
    validate_password("12345678")
    with pytest.raises(ValueError):
        validate_password("pass")
    with pytest.raises(ValueError):
        validate_password("")


def test_create_user_strips_non_public_groups(tmp_settings):
    uid = create_user("alice", "password1", ["hr", "evil"], force_groups=False)
    assert uid > 0
    from backend.l14_security.auth import authenticate

    u = authenticate("alice", "password1")
    assert u.groups == ["public"]  # self-register cannot grant hr


def test_create_user_force_groups(tmp_settings):
    create_user("luffy", "password1", ["hr", "public"], force_groups=True)
    from backend.l14_security.auth import authenticate

    u = authenticate("luffy", "password1")
    assert set(u.groups) == {"hr", "public"}


def test_duplicate_username_valueerror(tmp_settings):
    create_user("bob", "password1", ["public"], force_groups=True)
    with pytest.raises(ValueError, match="username taken"):
        create_user("bob", "password1", ["public"], force_groups=True)


def test_authenticate_bad_password(tmp_settings):
    create_user("carol", "password1", ["public"], force_groups=True)
    from backend.l14_security.auth import authenticate

    with pytest.raises(ValueError):
        authenticate("carol", "wrong-pass")


def test_mint_and_decode_roundtrip(tmp_settings):
    import jwt as pyjwt

    from backend.config import settings

    user = User(id=42, username="zoro", groups=["eng", "public"])
    token = mint(user)
    claims = pyjwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    assert claims["sub"] == "42"
    assert claims["username"] == "zoro"
    assert claims["groups"] == ["eng", "public"]
