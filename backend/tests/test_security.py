import pytest
from pydantic import ValidationError
from app.core.security import hash_password, verify_password
from app.core.permissions import may_manage_role
from app.schemas import BusinessInput, Register
from fastapi import HTTPException


def test_passwords_are_salted_and_verified():
    password = "  A long password!  "
    first = hash_password(password)
    assert first != hash_password(password)
    assert verify_password(password, first)
    assert not verify_password(password.strip(), first)
    assert not verify_password("another password", first)
    assert not verify_password(password, "malformed")


def test_password_whitespace_is_preserved():
    data = Register(email=" Test@EXAMPLE.com ", name=" Test ", password="  long secret  ")
    assert data.password == "  long secret  "
    assert data.email == "test@example.com"
    assert data.name == "Test"
    with pytest.raises(ValidationError):
        Register(email="test@example.com", name="Test", password="too short")


def test_profile_validation_and_defaults():
    data = dict(name="Restaurant", business_type="restaurant", country="IN", currency="INR", timezone="Asia/Kolkata")
    assert "ingredients" in BusinessInput(**data).modules
    for changes in [{"timezone": "not-a-timezone"}, {"reporting_month": 13}, {"modules": ["billable_hours"]}, {"modules": ["orders", "orders"]}, {"modules": []}]:
        with pytest.raises(ValidationError):
            BusinessInput(**(data | changes))


def test_administrators_cannot_grant_privileged_roles():
    assert may_manage_role("owner", "administrator")
    assert may_manage_role("administrator", "viewer")
    assert not may_manage_role("administrator", "owner")
    assert not may_manage_role("administrator", "administrator")
    assert not may_manage_role("viewer", "viewer")


def test_authentication_fails_closed_when_redis_is_unavailable(monkeypatch):
    from app.core.security import rate_limit
    def unavailable(*args, **kwargs):
        raise ConnectionError("sensitive connection details")
    monkeypatch.setattr("app.core.security.Redis.from_url", unavailable)
    with pytest.raises(HTTPException) as error:
        rate_limit("example", 1, 60)
    assert error.value.status_code == 503
    assert "sensitive" not in error.value.detail
