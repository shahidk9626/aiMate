"""Opaque secret tokens: session cookies, email links, invitations (ADR-023).

The raw token goes to the user exactly once (cookie or email link). The
database stores only its SHA-256 hash, so a database leak does not yield
usable sessions or links. 32 random bytes (256 bits) make guessing infeasible,
which is also why a fast hash (SHA-256) is appropriate here, unlike passwords.
"""

import hashlib
import secrets
from dataclasses import dataclass

TOKEN_BYTES = 32


@dataclass(frozen=True)
class IssuedToken:
    value: str  # URL-safe, given to the user
    digest: bytes  # SHA-256, stored in the database


def hash_token(value: str) -> bytes:
    return hashlib.sha256(value.encode("ascii", errors="ignore")).digest()


def issue_token() -> IssuedToken:
    value = secrets.token_urlsafe(TOKEN_BYTES)
    return IssuedToken(value=value, digest=hash_token(value))
