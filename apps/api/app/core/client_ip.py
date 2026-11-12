"""Client IP address for rate limiting and audit logs.

Locally and without a trusted proxy, the TCP peer address is used. Behind
Cloudflare (TRUSTED_PROXY=cloudflare) the CF-Connecting-IP header is used,
but only when it parses as an IP address. Never enable that setting when the
API can also be reached directly: anyone could then forge the header.
"""

import ipaddress

from fastapi import Request

from app.core.config import Settings


def client_ip(request: Request, settings: Settings) -> str | None:
    if settings.trusted_proxy == "cloudflare":
        raw = request.headers.get("cf-connecting-ip", "").strip()
        try:
            return str(ipaddress.ip_address(raw))
        except ValueError:
            pass
    return request.client.host if request.client else None
