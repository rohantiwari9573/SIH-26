from pydantic import BaseModel, EmailStr, Field, field_validator


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)

    @field_validator("password")
    @classmethod
    def _password_within_bcrypt_limit(cls, value: str) -> str:
        # bcrypt's 72-byte limit (app/core/security.py) is bytes, not
        # characters — a Pydantic max_length=72 would still let a password
        # with multi-byte UTF-8 characters (accents, emoji) through, which
        # would then hit pwd_context.hash() and raise an unhandled ValueError
        # ("password cannot be longer than 72 bytes"), 500ing instead of
        # failing with a clean 422. Check the actual encoded byte length.
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be at most 72 bytes when UTF-8 encoded")
        return value


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
