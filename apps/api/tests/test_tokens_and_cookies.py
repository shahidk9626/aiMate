import hashlib

import pytest
from fastapi import Response
from pydantic import SecretStr
from starlette.requests import Request

from app.core.client_ip import client_ip
from app.core.config import Environment, Settings
from app.modules.identity.cookies import (
    clear_session_cookie,
    read_session_cookie,
    set_session_cookie,
)
from app.modules.identity.tokens import hash_token, issue_token


def _settings(env: Environment = Environment.LOCAL, **extra: object) -> Settings:
    deployed = env in (Environment.STAGING, Environment.PRODUCTION)
    if deployed:
        extra.setdefault("app_db_password", SecretStr("x"))
        extra.setdefault("redis_password", SecretStr("x"))
        extra.setdefault("web_origin", "https://app.example.com")
    return Settings(_env_file=None, app_env=env, **extra)  # type: ignore[arg-type]


def _request(headers: dict[str, str] | None = None, peer: str = "10.1.2.3") -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request({"type": "http", "headers": raw, "client": (peer, 1234), "method": "GET"})


# --- tokens -------------------------------------------------------------------------


def test_issued_tokens_are_long_unique_and_hashed_with_sha256() -> None:
    tokens = [issue_token() for _ in range(1000)]

    assert len({t.value for t in tokens}) == 1000
    assert all(len(t.value) >= 43 for t in tokens)  # 32 bytes, URL-safe base64
    token = tokens[0]
    assert token.digest == hashlib.sha256(token.value.encode()).digest()
    assert hash_token(token.value) == token.digest
    assert token.value.encode() not in token.digest


# --- cookies --------------------------------------------------------------------------


def _set_cookie_header(settings: Settings) -> str:
    response = Response()
    set_session_cookie(response, settings, "tok")
    return response.headers["set-cookie"]


def test_local_cookie_is_httponly_lax_and_not_secure() -> None:
    header = _set_cookie_header(_settings(Environment.LOCAL))

    assert header.startswith("lf_session=tok;")
    assert "HttpOnly" in header
    assert "SameSite=lax" in header
    assert "Path=/" in header
    assert "Secure" not in header
    assert "Domain" not in header
    assert "Max-Age=2592000" in header  # 30 days


@pytest.mark.parametrize("env", [Environment.STAGING, Environment.PRODUCTION])
def test_deployed_cookie_uses_host_prefix_and_secure(env: Environment) -> None:
    header = _set_cookie_header(_settings(env))

    assert header.startswith("__Host-lf_session=tok;")
    assert "Secure" in header
    assert "HttpOnly" in header
    assert "Domain" not in header


def test_clearing_the_cookie_expires_it() -> None:
    response = Response()
    clear_session_cookie(response, _settings())

    header = response.headers["set-cookie"]
    assert header.startswith('lf_session="";')
    assert "Max-Age=0" in header


def test_read_session_cookie_rejects_empty_or_oversized_values() -> None:
    settings = _settings()

    assert read_session_cookie(_request({"cookie": "lf_session=abc"}), settings) == "abc"
    assert read_session_cookie(_request({"cookie": "other=abc"}), settings) is None
    assert read_session_cookie(_request({"cookie": f"lf_session={'a' * 300}"}), settings) is None


# --- client ip -------------------------------------------------------------------------


def test_client_ip_ignores_cloudflare_header_unless_trusted() -> None:
    request = _request({"cf-connecting-ip": "203.0.113.9"})

    assert client_ip(request, _settings()) == "10.1.2.3"
    assert client_ip(request, _settings(trusted_proxy="cloudflare")) == "203.0.113.9"


def test_client_ip_falls_back_when_cloudflare_header_is_invalid() -> None:
    request = _request({"cf-connecting-ip": "not-an-ip"})

    assert client_ip(request, _settings(trusted_proxy="cloudflare")) == "10.1.2.3"
