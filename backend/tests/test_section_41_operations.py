"""Section 41: synthetic tenant-only worker queue observations."""
from datetime import datetime,timezone,timedelta
from app.enterprise_models import OutboundMessage
from app.models import Conversation

def test_outbox_metrics_are_tenant_private(seeded):
    (client,auth,tids,Session),admin,patient,case=seeded
    other=auth("b")
    operator=auth("a","operator@example.test")
    path="/api/v1/operations-metrics/outbox"
    assert client.get(path).status_code==401
    assert client.get(path,headers=operator).status_code==403
    with Session() as db:
        conv=Conversation(tenant_id=tids[0],patient_id=patient["id"],channel="whatsapp")
        db.add(conv);db.flush()
        msg=OutboundMessage(tenant_id=tids[0],patient_id=patient["id"],
            conversation_id=conv.id,template_name="case_update_available",
            locale="fa",idempotency_key="section41-synthetic-outbox",
            status="approved",created_at=datetime.now(timezone.utc)-timedelta(hours=1))
        db.add(msg);db.commit()
    response=client.get(path,headers=admin)
    assert response.status_code==200,response.text
    data=response.json()
    assert data["counts"]["approved"]==1
    assert data["approved_older_than_15m"]==1
    assert data["production_slo_met"] is False
    assert patient["id"] not in response.text
    assert case["id"] not in response.text
    foreign=client.get(path,headers=other)
    assert foreign.status_code==200
    assert foreign.json()["counts"]["approved"]==0
    assert foreign.json()["approved_older_than_15m"]==0
