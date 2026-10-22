"""Container heartbeat check for an explicitly enabled outbound worker."""
import os
from .outbound_worker import HEARTBEAT_KEY


def healthy() -> bool:
    url = os.getenv("REDIS_URL", "")
    if not url.startswith(("redis://", "rediss://")):
        return False
    from redis import Redis
    client = Redis.from_url(url, socket_timeout=2, socket_connect_timeout=2)
    try:
        return client.get(HEARTBEAT_KEY) == b"running"
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(0 if healthy() else 1)
