"""UserCreate password validation — bcrypt hard-fails (ValueError, previously
unhandled -> 500) on passwords over 72 *bytes*. Pydantic's max_length counts
characters, not bytes, so this needs an explicit byte-length check to catch
multi-byte UTF-8 passwords too, not just long ASCII ones.
"""
import pytest
from pydantic import ValidationError

from app.schemas.auth import UserCreate


def test_password_within_limits_is_accepted():
    user = UserCreate(email="team@example.com", password="hunter2pass")
    assert user.password == "hunter2pass"


def test_password_too_short_is_rejected():
    with pytest.raises(ValidationError):
        UserCreate(email="team@example.com", password="short")


def test_password_over_72_ascii_bytes_is_rejected():
    with pytest.raises(ValidationError):
        UserCreate(email="team@example.com", password="a" * 73)


def test_password_exactly_72_ascii_bytes_is_accepted():
    user = UserCreate(email="team@example.com", password="a" * 72)
    assert len(user.password) == 72


def test_password_over_72_bytes_via_multibyte_utf8_is_rejected():
    # 40 chars, each a 2-byte UTF-8 character = 80 bytes, under Pydantic's
    # character-based max_length were it 72, but over bcrypt's byte limit —
    # exactly the case a naive max_length=72 on the str field would miss.
    password = "é" * 40
    assert len(password) < 72  # character count alone wouldn't catch this
    with pytest.raises(ValidationError):
        UserCreate(email="team@example.com", password=password)
