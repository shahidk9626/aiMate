import pytest
from argon2 import PasswordHasher

from app.modules.identity.passwords import (
    MAX_PASSWORD_LENGTH,
    PasswordPolicyError,
    hash_password,
    hash_password_async,
    validate_password,
    verify_dummy,
    verify_password,
    verify_password_async,
)

GOOD = "correct horse battery"


def test_hash_is_argon2id_and_salted() -> None:
    first, second = hash_password(GOOD), hash_password(GOOD)

    assert first.startswith("$argon2id$")
    assert first != second  # random salt per hash


def test_verify_accepts_right_and_rejects_wrong_password() -> None:
    stored = hash_password(GOOD)

    assert verify_password(stored, GOOD).ok
    assert not verify_password(stored, GOOD + "!").ok


def test_verify_tolerates_corrupt_hashes() -> None:
    assert not verify_password("not-a-hash", GOOD).ok


def test_needs_rehash_when_parameters_are_strengthened() -> None:
    weak = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1)
    stored = hash_password(GOOD, hasher=weak)

    result = verify_password(stored, GOOD)

    assert result.ok and result.needs_rehash
    assert not verify_password(hash_password(GOOD), GOOD).needs_rehash


def test_dummy_verification_always_fails() -> None:
    assert not verify_dummy(GOOD).ok


@pytest.mark.anyio
async def test_async_helpers_run_in_thread_and_handle_unknown_users() -> None:
    stored = await hash_password_async(GOOD)

    assert (await verify_password_async(stored, GOOD)).ok
    assert not (await verify_password_async(None, GOOD)).ok


@pytest.mark.parametrize(
    "password",
    [
        "a" * 10,  # minimum length
        "ünïcödé-pässwörd",  # any characters allowed
        "x" * MAX_PASSWORD_LENGTH,
        "lowercase only is fine",  # no composition rules (NIST 800-63B)
    ],
)
def test_policy_accepts(password: str) -> None:
    validate_password(password, email="owner@example.com")


@pytest.mark.parametrize(
    ("password", "fragment"),
    [
        ("short", "at least 10"),
        ("x" * (MAX_PASSWORD_LENGTH + 1), "at most 128"),
        ("Owner@Example.com", "email"),
    ],
)
def test_policy_rejects_with_field_details(password: str, fragment: str) -> None:
    with pytest.raises(PasswordPolicyError) as exc_info:
        validate_password(password, email="owner@example.com")

    error = exc_info.value
    assert error.status_code == 422
    assert error.code == "PASSWORD_POLICY"
    assert any(fragment in d["message"] for d in error.details)
    assert all(d["field"] == "password" for d in error.details)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
