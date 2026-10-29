import pytest
from pydantic import ValidationError
from app.core.config import Settings


def test_no_wildcard_cors():
    with pytest.raises(ValidationError):
        Settings(allowed_origins=["*"], _env_file=None)


def test_database_password_is_not_in_settings_repr():
    settings = Settings(database_url="postgresql+psycopg://user:private-secret@db/test", _env_file=None)
    assert "private-secret" not in repr(settings)
