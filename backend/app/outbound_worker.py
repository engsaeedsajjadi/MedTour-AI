"""Opt-in durable SQL outbox consumer. Never starts in a default Docker profile.

The outbox row is the durable queue; Redis is a dependency/heartbeat, not a PHI
broker. Only supervisor-approved GENERIC Meta templates may be dispatched.
Unknown provider outcome remains a manual reconciliation state, not a retry.
"""
from __future__ import annotations

import os
import time
from collections import Counter

from sqlalchemy import select

from .database import SessionLocal
from .enterprise_models import OutboundMessage
from .delivery import enabled as provider_enabled, send_one
from .safety_rules import assert_safe_runtime

HEARTBEAT_KEY = "medtour:worker:outbound:heartbeat"


def authorized() -> bool:
    return bool(
        os.getenv("APP_ENV", "development") != "production"
        and os.getenv("OUTBOUND_WORKER_ENABLED", "false").lower() == "true"
        and os.getenv("REDIS_URL", "").startswith(("redis://", "rediss://"))
        and provider_enabled()
    )


def _heartbeat() -> None:
    """Do not expose any patients, identifiers or tokens to Redis."""
    from redis import Redis
    client = Redis.from_url(
        os.environ["REDIS_URL"],
        socket_timeout=2,
        socket_connect_timeout=2,
        retry_on_timeout=False,
    )
    try:
        if not client.ping():
            raise RuntimeError("Redis heartbeat unavailable")
        client.set(HEARTBEAT_KEY, "running", ex=90)
    finally:
        client.close()


def poll_once(*, session_factory=None, sender=None, batch_size: int = 20) -> dict:
    if not 1 <= batch_size <= 100:
        raise ValueError("batch_size must be within 1..100")
    if not authorized():
        return {"status": "disabled", "processed": 0}
    _heartbeat()
    make_session = session_factory or SessionLocal
    dispatch = sender or send_one
    with make_session() as db:
        # The DB outbox is the durable source. send_one() atomically claims
        # approved rows, so overlapping workers cannot dispatch twice.
        ids = list(db.scalars(
            select(OutboundMessage.id)
            .where(OutboundMessage.status == "approved")
            .order_by(OutboundMessage.created_at, OutboundMessage.id)
            .limit(batch_size)
        ).all())
    counts = Counter()
    for oid in ids:
        result = dispatch(oid)
        counts[result.get("status", "unknown")] += 1
    return {"status": "running", "processed": len(ids), "results": dict(counts)}


def run_forever() -> None:
    assert_safe_runtime()
    if not authorized():
        raise RuntimeError("Outbound worker disabled until explicit provider, consent and operator approvals")
    seconds = int(os.getenv("OUTBOUND_WORKER_POLL_SECONDS", "5"))
    batch_size = int(os.getenv("OUTBOUND_WORKER_BATCH_SIZE", "20"))
    if not (1 <= seconds <= 300 and 1 <= batch_size <= 100):
        raise RuntimeError("Unsafe worker batch/interval configuration")
    while True:
        poll_once(batch_size=batch_size)
        time.sleep(seconds)


if __name__ == "__main__":
    run_forever()
