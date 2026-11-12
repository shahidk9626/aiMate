"""Client IP address for rate limiting and audit logs.

Locally and without a trusted proxy, the TCP peer address is used. Behind
Cloudflare (TRUSTED_PROXY=cloudflare) the CF-Connecting-IP header is used,
but only when it parses as an IP address. Never enable that setting when the
API can also be reached directly: anyone could then forge the header.
"""

import ipaddress

from fastapi import Request

from app.core.config import Settings


def _valid_ip(raw: str | None) -> str | None:
    try:
        return str(ipaddress.ip_address((raw or "").strip()))
    except ValueError:
        return None


def client_ip(request: Request, settings: Settings) -> str | None:
    """A valid IP address string, or None (stored in INET columns and rate-limit keys)."""
    if settings.trusted_proxy == "cloudflare":
        forwarded = _valid_ip(request.headers.get("cf-connecting-ip"))
        if forwarded:
            return forwarded
    return _valid_ip(request.client.host) if request.client else None
