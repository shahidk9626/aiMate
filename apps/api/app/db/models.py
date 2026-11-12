"""Model registry.

Import every module that defines ORM models here so Alembic autogenerate and
the drift test see the complete metadata.
"""

from app.modules.audit.models import AuditLog
from app.modules.identity.models import AuthSession, EmailToken, User
from app.modules.outbox.models import OutboxEvent
from app.modules.tenancy.models import Invitation, Membership, Tenant

__all__ = [
    "AuditLog",
    "AuthSession",
    "EmailToken",
    "Invitation",
    "Membership",
    "OutboxEvent",
    "Tenant",
    "User",
]
