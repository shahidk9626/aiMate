"""The verified tenant context and role ranking.

Kept free of HTTP and identity imports so services can depend on it without
import cycles; the FastAPI dependency that builds it lives in dependencies.py.
"""

import uuid
from dataclasses import dataclass

from app.core.errors import PermissionDeniedError
from app.modules.tenancy.models import Role

ROLE_RANK = {Role.AGENT: 1, Role.ADMIN: 2, Role.OWNER: 3}


@dataclass(frozen=True)
class TenantContext:
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    role: Role

    def has(self, minimum: Role) -> bool:
        return ROLE_RANK[self.role] >= ROLE_RANK[minimum]

    def require(self, minimum: Role) -> None:
        if not self.has(minimum):
            raise PermissionDeniedError()
