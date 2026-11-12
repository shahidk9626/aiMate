"""Structured logging.

All log output (ours, uvicorn's, libraries') goes through structlog so every
line is JSON in deployed environments and carries the request id.

Privacy rule: never log message bodies, request bodies, query strings, emails,
phone numbers, tokens or credentials. Log identifiers, not content.
"""

import logging
import sys
from typing import Any

import structlog
from structlog.types import EventDict

from app.core.config import Settings

# Keys whose values are replaced before any log line is rendered. A guard rail
# for mistakes, not a licence to log sensitive data.
_REDACTED_KEYS = frozenset(
    {
        "password",
        "password_hash",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "cookie",
        "secret",
        "api_key",
        "credentials",
    }
)


def _redact(_: Any, __: str, event_dict: EventDict) -> EventDict:
    for key in event_dict.keys() & _REDACTED_KEYS:
        event_dict[key] = "[REDACTED]"
    return event_dict


def configure_logging(settings: Settings) -> None:
    shared: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _redact,
    ]
    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer()
        if settings.use_json_logs
        else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            renderer,
        ],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level)

    # uvicorn installs its own handlers; route them through ours instead.
    # Its access log is disabled: our middleware writes one line per request
    # without the query string (which can contain personal data).
    for name in ("uvicorn", "uvicorn.error"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers.clear()
        uv_logger.propagate = True
    logging.getLogger("uvicorn.access").disabled = True


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.stdlib.get_logger(name)
