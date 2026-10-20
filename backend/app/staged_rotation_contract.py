"""Stage 19.24: non-privileged credential-rotation preflight, staged only.

This code never changes PostgreSQL passwords, grants rights, or terminates
connections. A separate least-privilege control-plane operator MUST validate
the epoch and role again transactionally inside PostgreSQL before rotation.
"""
from __future__ import annotations

from dataclasses import dataclass

from .staged_tenant_epoch_control import EpochReader, EpochState
from .staged_tenant_pool_registry import TenantPrincipalConfig


@dataclass(frozen=True)
class RotationHandoff:
    tenant_id: str
    from_generation: int
    to_generation: int
    database_role: str


def prepare_rotation(
    *,
    reader: EpochReader,
    old: TenantPrincipalConfig,
    replacement: TenantPrincipalConfig,
    disabled_generation: int,
) -> RotationHandoff:
    """Fail closed unless exactly one trusted disabled epoch controls cutover.

    Do not cache this result; passing preflight does not authorize role DDL.
    Secrets intentionally do not appear in the returned handoff or repr.
    """
    if not isinstance(old, TenantPrincipalConfig) or not isinstance(
        replacement, TenantPrincipalConfig
    ):
        raise ValueError("Both provisioning inputs must be trusted configs")
    if type(disabled_generation) is not int or disabled_generation < 2:
        raise ValueError("Invalid disabled epoch")
    if not callable(getattr(reader, "read", None)):
        raise ValueError("Authenticated central epoch reader required")
    if any(
        getattr(old, field) != getattr(replacement, field)
        for field in (
            "tenant_id", "slug", "whatsapp_phone_id", "database_role",
            "database_host", "database_port", "database_name",
        )
    ):
        raise ValueError("Credential-only rotation cannot change tenant identity or DB endpoint")
    if old.database_password == replacement.database_password:
        raise ValueError("Replacement password must differ from current password")
    try:
        state = reader.read(old.tenant_id)
    except Exception as exc:
        raise LookupError("Central epoch authority unavailable") from exc
    if state != EpochState(disabled_generation, False):
        raise LookupError("Rotation requires an exactly matched disabled tenant epoch")
    return RotationHandoff(
        tenant_id=old.tenant_id,
        from_generation=disabled_generation - 1,
        to_generation=disabled_generation + 1,
        database_role=old.database_role,
    )
