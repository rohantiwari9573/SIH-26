"""get_current_user previously called uuid.UUID(subject) unguarded — a
validly-signed token should always carry a UUID "sub" (minted from
str(user.id)), but a malformed one shouldn't 500 instead of failing closed
with a clean 401.
"""
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_current_user
from app.core.security import create_access_token
from app.db.base import Base


def _session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'deps_test.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_malformed_uuid_subject_raises_401_not_valueerror(tmp_path):
    token = create_access_token(subject="not-a-valid-uuid")
    db = _session(tmp_path)

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(token=token, db=db)

    assert exc_info.value.status_code == 401
