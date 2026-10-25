"""Synthetic human inbox Section 11 tests; no external provider or actual PHI."""
from app.enterprise_models import InboxThread, InboxAction
from app.models import Conversation, Message, Audit

BASE = "/api/v1/inbox"


def _comm(client, admin, patient_id, accepted=True):
    result = client.post("/api/v1/consents", headers=admin, json={
        "patient_id": patient_id, "purpose": "communication",
        "accepted": accepted, "notice_version": "v11",
    })
    assert result.status_code == 201, result.text


def _portal(client, admin, patient_id):
    _comm(client, admin, patient_id)
    r = client.post("/api/v1/portal/invites/" + patient_id, headers=admin)
    assert r.status_code == 201
    exchange=client.post("/api/v1/portal/session/exchange",json={
        "invitation_token":r.json()["token"],
        "verification_code":r.json()["demo_verification_code"]})
    assert exchange.status_code==201,exchange.text
    return {"X-Patient-Access":exchange.json()["access_token"]}


def _chat(client, portal, phrase="Hello"):
    r = client.post("/api/v1/portal/chat", headers=portal,
                    json={"language":"en","message":phrase})
    assert r.status_code == 201, r.text
    return r.json()


def test_inbox_staff_only_privacy_and_tenant_isolation(seeded):
    (client,auth,ids,Session),admin,p,case=seeded
    portal = _portal(client,admin,p["id"])
    sent = _chat(client,portal,"I need help with a visa")
    cid = sent["conversation_id"]
    operator = auth("a","operator@example.test")
    assert client.get(BASE+"/threads").status_code == 401
    assert client.get(BASE+"/threads",headers=auth("b")).json()["items"] == []
    assert client.get(BASE+"/threads",headers=operator).status_code == 200
    assert client.get(BASE+f"/threads/{cid}/messages",headers=operator).status_code == 403
    assert client.get(BASE+f"/threads/{cid}/events",headers=operator).status_code == 403
    assert client.get("/api/v1/conversations/"+cid+"/messages",headers=operator).status_code == 403
    listing = client.get(BASE+"/threads",headers=admin)
    assert listing.status_code == 200,listing.text
    assert listing.json()["items"][0]["conversation_id"] == cid
    assert listing.json()["medical_content_included"] is False
    assert "visa" not in str(listing.json())
    assert client.get(BASE+f"/threads/{cid}/messages",
                      headers=auth("b")).status_code == 404
    assert client.post(BASE+f"/threads/{cid}/claim",
                       headers=auth("b")).status_code == 404
    ready = client.get(BASE+"/readiness",headers=admin)
    assert ready.status_code == 200
    assert not ready.json()["chatwoot_sync_live_verified"]
    assert not ready.json()["live_whatsapp_send_verified"]
    assert not ready.json()["real_patient_data_allowed"]


def test_operator_claim_reply_and_admin_assignment_cannot_be_hijacked(seeded):
    (client,auth,ids,Session),admin,p,case=seeded
    portal=_portal(client,admin,p["id"])
    cid=_chat(client,portal,"Human please")["conversation_id"]
    op=auth("a","operator@example.test")
    op_id=client.get("/api/v1/auth/me",headers=op).json()["id"]
    admin_id=client.get("/api/v1/auth/me",headers=admin).json()["id"]
    url=BASE+f"/threads/{cid}"
    assert client.post(url+"/reply",headers=op,
        json={"language":"en","body":"We will coordinate."}).status_code == 403
    first=client.post(url+"/claim",headers=op)
    assert first.status_code == 200, first.text
    assert first.json()["assigned_user_id"] == op_id
    assert client.post(url+"/claim",headers=op).json()["reused"] is True
    staff_msg=client.post(url+"/reply",headers=op,
        json={"language":"ar","body":"مرحبا. سنتابع الطلب."})
    assert staff_msg.status_code == 201, staff_msg.text
    assert staff_msg.json()["stored_in_portal"] is True
    assert staff_msg.json()["external_provider_sent"] is False
    assert client.post("/api/v1/conversations/"+cid+"/messages",headers=admin,
        json={"body":"Legacy guarded path","language":"en"}).status_code == 201
    assert client.post(url+"/assign",headers=op,
        json={"assigned_user_id":admin_id}).status_code == 403
    changed=client.post(url+"/assign",headers=admin,
        json={"assigned_user_id":admin_id})
    assert changed.status_code == 200, changed.text
    assert client.get(BASE+"/threads?assigned=mine",headers=op).json()["items"] == []
    assert client.get(url+"/messages",headers=op).status_code == 403
    assert client.post("/api/v1/conversations/"+cid+"/handoff",headers=op).status_code == 403
    assert client.post("/api/v1/conversations/"+cid+"/messages",headers=op,
        json={"body":"ILLEGAL takeover","language":"en"}).status_code == 403
    assert client.post(url+"/reply",headers=op,
        json={"body":"ILLEGAL","language":"en"}).status_code == 403
    history=client.get(url+"/events",headers=admin)
    assert history.status_code == 200
    assert "مرحبا" not in str(history.json())
    assert any(x["action"]=="reassigned" for x in history.json()["items"])
    with Session() as db:
        assert db.query(InboxThread).count()==1
        assert db.query(InboxAction).count()>=3


def test_wait_resolve_reopen_and_automatic_bot_never_reactivates(seeded):
    (client,auth,ids,Session),admin,p,case=seeded
    portal=_portal(client,admin,p["id"])
    cid=_chat(client,portal,"I want a human operator")["conversation_id"]
    url=BASE+f"/threads/{cid}"
    assert client.post(url+"/claim",headers=admin).status_code == 200
    waiting=client.post(url+"/wait",headers=admin,json={"reference":"FOLLOWUP-REF-011"})
    assert waiting.status_code==200 and waiting.json()["status"]=="waiting"
    closed=client.post(url+"/resolve",headers=admin,json={"reference":"CLOSE-REF-011"})
    assert closed.status_code==200, closed.text
    assert closed.json()["status"]=="resolved"
    assert closed.json()["bot_reactivated"] is False
    assert client.post(url+"/reply",headers=admin,
        json={"language":"en","body":"Should be blocked"}).status_code == 409
    assert client.post(url+"/resolve",headers=admin,
        json={"reference":"CLOSE-REF-011"}).status_code == 409
    reopened=client.post(url+"/reopen",headers=admin,
        json={"reference":"REOPEN-REF-011"})
    assert reopened.status_code == 200
    assert reopened.json()["status"]=="assigned"
    assert client.post(url+"/wait",headers=admin,json={
        "reference":"contains medical name"}).status_code == 422
    again=client.post(url+"/resolve",headers=admin,
        json={"reference":"CLOSE-REF-012"})
    assert again.status_code == 200
    incoming=_chat(client,portal,"Still need help")
    assert incoming["conversation_id"] == cid
    assert incoming["automated_response"] is None
    state=client.get(BASE+"/threads",headers=admin).json()["items"][0]
    assert state["status"]=="assigned"
    assert state["human_handoff"] is True
    assert state["priority"]=="normal"
    trail=client.get(url+"/events",headers=admin).json()["items"]
    assert any(x["action"]=="patient_reopened" for x in trail)
    assert any(x["reference"]=="CLOSE-REF-011" for x in trail)


def test_urgent_webchat_sets_nonclinical_priority_and_never_autoclears(seeded):
    (client,auth,ids,Session),admin,p,case=seeded
    portal=_portal(client,admin,p["id"])
    event=_chat(client,portal,"I have severe bleeding")
    assert event["warning"]
    assert event["automated_response"] is None
    cid=event["conversation_id"]
    queue=client.get(BASE+"/threads",headers=admin).json()["items"]
    assert queue[0]["priority"]=="urgent"
    assert queue[0]["human_handoff"] is True
    assert "bleeding" not in str(queue)
    resolved=client.post(BASE+f"/threads/{cid}/resolve",
        headers=admin,json={"reference":"EMERGENCY-ACK-011"})
    assert resolved.status_code==200
    assert resolved.json()["external_delivery_confirmed"] is False
    next_event=_chat(client,portal,"Additional message")
    assert next_event["automated_response"] is None
    assert client.get(BASE+"/threads",headers=admin).json()["items"][0]["priority"]=="urgent"


def test_consent_withdrawal_blocks_historical_read_reply_and_translation(seeded):
    (client,auth,ids,Session),admin,p,case=seeded
    portal=_portal(client,admin,p["id"])
    cid=_chat(client,portal)["conversation_id"]
    url=BASE+f"/threads/{cid}"
    assert client.post(url+"/claim",headers=admin).status_code==200
    assert client.get(url+"/messages",headers=admin).status_code==200
    _comm(client,admin,p["id"],accepted=False)
    assert client.get(url+"/messages",headers=admin).status_code==409
    assert client.get("/api/v1/conversations/"+cid+"/messages",headers=admin).status_code==409
    assert client.post(url+"/reply",headers=admin,
        json={"language":"en","body":"Not permitted"}).status_code==409
    assert client.post(url+"/claim",headers=admin).status_code==409
    assert client.get(BASE+"/threads",headers=admin).json()["items"]==[]
    assert client.post("/api/v1/communications/translation-drafts",headers=admin,json={
        "conversation_id":cid, "source_language":"en","target_language":"ar",
        "source_text":"no permission"
    }).status_code==409
    _comm(client,admin,p["id"])
    assert client.get(url+"/messages",headers=admin).status_code==200


def test_whatsapp_freeform_rejected_and_no_live_chatwoot_false_claim(seeded):
    (client,auth,ids,Session),admin,p,case=seeded
    _comm(client,admin,p["id"])
    created=client.post("/api/v1/conversations",headers=admin,
                        json={"patient_id":p["id"]})
    assert created.status_code==201
    cid=created.json()["id"]
    with Session() as db:
        c=db.get(Conversation,cid)
        c.channel="whatsapp"
        db.commit()
    url=BASE+f"/threads/{cid}"
    assert client.post(url+"/claim",headers=admin).status_code==200
    denied=client.post(url+"/reply",headers=admin,
                       json={"language":"fa","body":"Freeform WhatsApp message"})
    assert denied.status_code==409
    assert client.post("/api/v1/conversations/"+cid+"/messages",
        headers=admin,json={"language":"fa","body":"Legacy bypass"}).status_code==409
    assert client.get(BASE+"/readiness",headers=admin).json()["chatwoot_sync_configured"] is False
    with Session() as db:
        assert db.query(Message).filter(Message.conversation_id==cid).count()==0


def test_admin_can_release_and_reassign_and_foreign_staff_rejected(seeded):
    (client,auth,ids,Session),admin,p,case=seeded
    portal=_portal(client,admin,p["id"])
    cid=_chat(client,portal)["conversation_id"]
    op=auth("a","operator@example.test")
    op_id=client.get("/api/v1/auth/me",headers=op).json()["id"]
    foreign_id=client.get("/api/v1/auth/me",headers=auth("b")).json()["id"]
    url=BASE+f"/threads/{cid}"
    assert client.post(url+"/assign",headers=admin,
        json={"assigned_user_id":foreign_id}).status_code==404
    assert client.post(url+"/assign",headers=admin,
        json={"assigned_user_id":op_id}).status_code==200
    released=client.post(url+"/release",headers=op)
    assert released.status_code==200
    assert released.json()["assigned_user_id"] is None
    claimed=client.post(url+"/claim",headers=admin)
    assert claimed.status_code==200
    assert claimed.json()["assigned_user_id"]!=op_id


def test_legacy_handoff_admin_before_consent_preserves_old_compatibility(seeded):
    (client,auth,ids,Session),admin,p,case=seeded
    conv=client.post("/api/v1/conversations",headers=admin,json={"patient_id":p["id"]})
    assert conv.status_code==201
    cid=conv.json()["id"]
    handoff=client.post("/api/v1/conversations/"+cid+"/handoff",headers=admin)
    assert handoff.status_code==200, handoff.text
    assert handoff.json()["human_handoff"] is True
    _comm(client,admin,p["id"])
    assert client.post("/api/v1/conversations/"+cid+"/messages",
        headers=admin,json={"body":"Synthetic safe webchat response","language":"en"}
    ).status_code==201
