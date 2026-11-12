"""Success envelope (docs/API_CONTRACTS.md): {"data": ..., "meta": {"request_id": ...}}.

Errors use the error envelope in app.core.errors. Health probes are not enveloped.
"""

from fastapi import Request
from pydantic import BaseModel


class Meta(BaseModel):
    request_id: str | None = None


class Envelope[T](BaseModel):
    data: T
    meta: Meta


def envelope[T](request: Request, data: T) -> Envelope[T]:
    return Envelope[T](data=data, meta=Meta(request_id=getattr(request.state, "request_id", None)))
