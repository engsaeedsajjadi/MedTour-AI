"""Synthetic Worker/dispatch tenant scoping regression tests."""
from uuid import uuid4
import pytest
from app.models import Patient,Conversation
from app.enterprise_models import OutboundMessage
from app import outbound_worker,delivery
from app import tenant_scoped_worker
from app.staged_tenant_epoch_control import StagedCoordinatedTenantRegistry,EpochState
from test_stage_19_22_tenant_registry import FakeBuilder,config,TID_A,TID_B

def test_global_worker_and_delivery_fail_closed_under_strict_mode(monkeypatch):
    monkeypatch.setenv("TENANT_DB_ROUTING_MODE","strict")
    monkeypatch.setattr(outbound_worker,"authorized",lambda:True)
    monkeypatch.setattr(delivery,"enabled",lambda:True)
    assert outbound_worker.poll_once()["status"]=="blocked"
    assert delivery.send_one(str(uuid4()))["status"]=="blocked"
    with pytest.raises(RuntimeError,match="Legacy global worker"):
        outbound_worker.run_forever()
    with pytest.raises(ValueError):
        outbound_worker.poll_once(session_factory=lambda:None)
    with pytest.raises(ValueError):
        delivery.send_one(str(uuid4()),expected_tenant_id=TID_A)

def test_polling_scans_only_its_provisioned_tenant(context,monkeypatch):
    _,_,tids,Session=context
    monkeypatch.setenv("TENANT_DB_ROUTING_MODE","strict")
    monkeypatch.setattr(outbound_worker,"authorized",lambda:True)
    monkeypatch.setattr(outbound_worker,"_heartbeat",lambda:None)
    ids=[]
    with Session() as db:
        for i in range(2):
            p=Patient(tenant_id=tids[i],full_name="Synthetic",country="",language="fa",contact="")
            db.add(p);db.flush()
            chat=Conversation(tenant_id=tids[i],patient_id=p.id,channel="whatsapp")
            db.add(chat);db.flush()
            row=OutboundMessage(tenant_id=tids[i],patient_id=p.id,conversation_id=chat.id,
                idempotency_key="synthetic-"+str(i),template_name="generic",locale="fa",
                status="approved")
            db.add(row);db.flush()
            ids.append(row.id)
        db.commit()
    sent=[]
    result=outbound_worker.poll_once(session_factory=Session,tenant_id=tids[0],
        sender=lambda oid:sent.append(oid) or {"status":"review_only"})
    assert result["status"]=="running" and result["processed"]==1
    assert sent==[ids[0]]
    sent.clear()
    result=outbound_worker.poll_once(session_factory=Session,tenant_id=tids[1],
        sender=lambda oid:sent.append(oid) or {"status":"review_only"})
    assert result["processed"]==1 and sent==[ids[1]]

class MemoryEpoch:
    def __init__(self):self.state={TID_A:EpochState(1,True)}
    def read(self,tenant_id):return self.state.get(tenant_id)

def test_guarded_worker_rejects_unprovisioned_and_revoked_epoch(monkeypatch):
    authority=MemoryEpoch()
    registry=StagedCoordinatedTenantRegistry(reader=authority,
        engine_builder=FakeBuilder(),max_tenants=2,pool_size=1)
    registry.provision(config(),generation=1)
    calls=[]
    monkeypatch.setattr(tenant_scoped_worker,"poll_once",lambda **kw:
        calls.append((kw["tenant_id"],kw["batch_size"])) or {"status":"inert"})
    assert tenant_scoped_worker.poll_provisioned_tenant(
        registry=registry,tenant_id=TID_A,batch_size=4)=={
        "status":"provider_binding_required","processed":0,
        "reason":"Strict mode cannot use global Meta credentials"}
    try:
        assert tenant_scoped_worker.poll_provisioned_tenant(
            registry=registry,tenant_id=TID_A,batch_size=4,
            sender=lambda _:{"status":"synthetic"})["status"]=="inert"
        assert calls==[(TID_A,4)]
        with pytest.raises(LookupError):
            tenant_scoped_worker.poll_provisioned_tenant(registry=registry,tenant_id=TID_B,
                sender=lambda _:{"status":"synthetic"})
        authority.state[TID_A]=EpochState(2,False)
        with pytest.raises(LookupError):
            tenant_scoped_worker.poll_provisioned_tenant(registry=registry,tenant_id=TID_A,
                sender=lambda _:{"status":"synthetic"})
        assert calls==[(TID_A,4)]
    finally:registry.close()

def test_strict_mode_disables_shared_get_db_and_tenant_global_meta_sender(context,monkeypatch):
    from app.database import get_db
    _,_,tenants,Session=context
    monkeypatch.setenv("TENANT_DB_ROUTING_MODE","strict")
    monkeypatch.setattr(delivery,"enabled",lambda:True)
    with pytest.raises(RuntimeError,match="verified request-bound"):
        next(get_db())
    # Even with a restricted tenant DB factory, the legacy global Meta
    # credentials cannot dispatch through a strict-mode worker.
    result=delivery.send_one(str(uuid4()),
        tenant_session_factory=Session,expected_tenant_id=tenants[0])
    assert result["status"]=="blocked"
    assert "Tenant-specific Meta" in result["reason"]
