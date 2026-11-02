"""Section 30: synthetic staff-only notification safety."""
from sqlalchemy import select
from app.models import User,Audit
from app.enterprise_models import Notification

def test_private_inbox_tenant_roles_and_read(context):
    client,auth,tids,Session=context
    a,b=auth("a"),auth("b")
    operator=auth("a","operator@example.test")
    with Session() as db:
        recipient=db.scalar(select(User).where(User.tenant_id==tids[0],User.role=="operator"))
        foreign=db.scalar(select(User).where(User.tenant_id==tids[1],User.role=="admin"))
        rid=recipient.id;fid=foreign.id
    base="/api/v1/workflow-notifications"
    payload={"recipient_id":rid,"kind":"task_review","reference_id":"synthetic-abc"}
    assert client.post(base,headers=operator,json=payload).status_code==403
    assert client.post(base,headers=b,json=payload).status_code==404
    assert client.post(base,headers=a,json=payload|{"recipient_id":fid}).status_code==404
    assert client.post(base,headers=a,json=payload|{"freeform_patient_text":"private"}).status_code==422
    created=client.post(base,headers=a,json=payload)
    assert created.status_code==201,created.text
    data=created.json();nid=data["id"]
    assert data["external_delivery"] is False
    assert "synthetic-abc" not in str(data)
    assert client.get(base,headers=a).json()["items"]==[]
    assert client.get(base,headers=b).json()["items"]==[]
    assert len(client.get(base,headers=operator,params={"unread_only":True}).json()["items"])==1
    assert client.post(base+"/"+nid+"/read",headers=a).status_code==404
    assert client.post(base+"/"+nid+"/read",headers=b).status_code==404
    assert client.post(base+"/"+nid+"/read",headers=operator).json()["read"] is True
    assert client.post(base+"/"+nid+"/read",headers=operator).status_code==200
    assert client.get(base,headers=operator,params={"unread_only":True}).json()["items"]==[]
    with Session() as db:
        assert db.get(Notification,nid).body==""
        records=db.scalars(select(Audit).where(Audit.entity_id==nid)).all()
        assert sorted(x.event for x in records)==[
            "internal_staff_notification_created","internal_staff_notification_read"]
