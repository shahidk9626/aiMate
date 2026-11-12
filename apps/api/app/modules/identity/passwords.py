"""Password policy and hashing (ADR-004, ADR-023 decision E).

- Argon2id via argon2-cffi with its RFC 9106 default profile
  (64 MiB, 3 passes, 4 lanes).
- Hashing is CPU-heavy (tens of milliseconds by design), so the async
  helpers run it in a worker thread and never block the event loop.
- Verifying against an unknown account still performs one full hash
  (``verify_dummy``), so response time does not reveal whether an email exists.
- ``needs_rehash`` tells the caller to store a fresh hash after a successful
  login when the parameters have been strengthened.
"""

from dataclasses import dataclass

from anyio import to_thread
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.errors import AppError

MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 128

_hasher = PasswordHasher()
# Hash of a random throwaway password, used to spend equal time on unknown users.
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing-equalisation")


class PasswordPolicyError(AppError):
    status_code = 422
    code = "PASSWORD_POLICY"
    message = "The password does not meet the requirements."


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    needs_rehash: bool = False


def validate_password(password: str, *, email: str | None = None) -> None:
    """Raise PasswordPolicyError with field details if the password is not acceptable."""
    problems: list[str] = []
    if len(password) < MIN_PASSWORD_LENGTH:
        problems.append(f"Use at least {MIN_PASSWORD_LENGTH} characters.")
    if len(password) > MAX_PASSWORD_LENGTH:
        problems.append(f"Use at most {MAX_PASSWORD_LENGTH} characters.")
    if email and password.strip().casefold() == email.strip().casefold():
        problems.append("The password must not be your email address.")
    if problems:
        raise PasswordPolicyError(
            details=[
                {"field": "password", "message": m, "type": "password_policy"} for m in problems
            ]
        )


def hash_password(password: str, hasher: PasswordHasher = _hasher) -> str:
    return hasher.hash(password)


def verify_password(
    password_hash: str, password: str, hasher: PasswordHasher = _hasher
) -> VerifyResult:
    try:
        hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return VerifyResult(ok=False)
    return VerifyResult(ok=True, needs_rehash=hasher.check_needs_rehash(password_hash))


def verify_dummy(password: str) -> VerifyResult:
    """Same cost as a real verification; always fails."""
    verify_password(_DUMMY_HASH, password)
    return VerifyResult(ok=False)


async def hash_password_async(password: str) -> str:
    return await to_thread.run_sync(hash_password, password)


async def verify_password_async(password_hash: str | None, password: str) -> VerifyResult:
    """Verify against a stored hash, or spend equal time when there is none."""
    if password_hash is None:
        return await to_thread.run_sync(verify_dummy, password)
    return await to_thread.run_sync(verify_password, password_hash, password)
