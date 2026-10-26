"""Trusted tenant-scoped outbound polling for the synthetic cutover pilot.

Only the provisioning control plane may supply tenant IDs and registry.
No global SessionLocal, tenant identifiers from message payload or dynamic
DB URLs are accepted. Each transaction obtains an epoch-checked lease.
"""
from __future__ import annotations
from .staged_epoch_preauth_bridge import EpochGuardedSessionFactory
from .staged_tenant_epoch_control import StagedCoordinatedTenantRegistry
from .outbound_worker import poll_once

def poll_provisioned_tenant(*,registry:StagedCoordinatedTenantRegistry,
                            tenant_id:str,batch_size:int=20,sender=None):
    if not isinstance(registry,StagedCoordinatedTenantRegistry):
        raise ValueError("Only vetted epoch-guarded registry is allowed")
    # Acquiring here prevents malformed/unprovisioned/revoked tenant IDs from
    # reaching any worker SQL or external provider.
    with registry.acquire_tenant(tenant_id) as lease:
        if lease.tenant_id!=tenant_id:
            raise PermissionError("Tenant lease mapping mismatch")
    factory=EpochGuardedSessionFactory(registry,tenant_id)
    return poll_once(session_factory=factory,tenant_id=tenant_id,
                     batch_size=batch_size,sender=sender)
