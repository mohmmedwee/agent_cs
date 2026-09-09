"""Password hashing and session tokens.

Argon2id for passwords: it is memory-hard, which is the property that matters
against GPU cracking, and it carries its parameters inside the hash string so
they can be raised later without a migration.

Sessions are signed cookies rather than rows in a table. The tradeoff is
honest: they cannot be revoked before they expire. That is acceptable here and
avoids a database read on every request; swap in stored tokens if revocation
becomes a requirement.
"""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

__all__ = ["PasswordHasherService", "SessionTokenService"]

_SALT = "agent-console.session"


class PasswordHasherService:
    def __init__(self) -> None:
        self._hasher = PasswordHasher()

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password: str, hashed: str) -> bool:
        try:
            self._hasher.verify(hashed, password)
        except (VerifyMismatchError, InvalidHashError):
            return False
        return True

    def needs_rehash(self, hashed: str) -> bool:
        try:
            return self._hasher.check_needs_rehash(hashed)
        except InvalidHashError:
            return False


class SessionTokenService:
    def __init__(self, secret: str, max_age_seconds: int) -> None:
        self._serializer = URLSafeTimedSerializer(secret, salt=_SALT)
        self._max_age = max_age_seconds

    def issue(self, user_id: str) -> str:
        return self._serializer.dumps({"uid": user_id})

    def read(self, token: str) -> str | None:
        """The user id inside a valid, unexpired token, else None."""
        try:
            payload = self._serializer.loads(token, max_age=self._max_age)
        except (BadSignature, SignatureExpired):
            return None
        user_id = payload.get("uid") if isinstance(payload, dict) else None
        return str(user_id) if user_id else None
