"""Development-only, allowlisted Telegram long-polling worker.

The worker never creates patient records, stores message content, accesses the
clinical database, or treats Telegram as a secure patient portal. It is
deliberately NOT a production-ready bot deployment.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import secrets
from dataclasses import dataclass

import httpx
from redis.asyncio import Redis

from . import telegram


@dataclass(frozen=True)
class PollingConfig:
    token: str
    chat_id: int
    redis_url: str
    secret: str
    privacy_url: str


def config_from_env() -> PollingConfig | None:
    """Fail closed outside explicitly opted-in local development."""
    if (
        os.getenv("APP_ENV") != "development"
        or os.getenv("TELEGRAM_POLLING_ENABLED", "").lower() != "true"
        or os.getenv("TELEGRAM_POLLING_TEST_MODE", "").lower() != "true"
        or os.getenv("TELEGRAM_BOT_ENABLED", "false").lower() == "true"
    ):
        return None
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    raw_chat_id = os.getenv("TELEGRAM_POLLING_CHAT_ID", "")
    secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
    redis_url = os.getenv("REDIS_URL", "")
    privacy_url = os.getenv("PUBLIC_PRIVACY_NOTICE_URL", "")
    if (
        not telegram._BOT_TOKEN.fullmatch(token)
        or not raw_chat_id.isascii() or not raw_chat_id.isdecimal()
        or not 0 < len(raw_chat_id) <= 20
        or int(raw_chat_id) <= 0 or int(raw_chat_id) > 2**63 - 1
        or not telegram._SECRET.fullmatch(secret)
        or not redis_url.startswith(("redis://", "rediss://"))
        or (privacy_url and not telegram._public_https_url(privacy_url))
    ):
        return None
    return PollingConfig(token, int(raw_chat_id), redis_url, secret, privacy_url)


def _endpoint(token: str, method: str) -> str:
    return "https://api.telegram.org/bot" + token + "/" + method


def _redacted_key(token: str, kind: str) -> str:
    return "medtour:telegram:dev-poller:" + kind + ":" + hashlib.sha256(token.encode("ascii")).hexdigest()


async def _telegram_call(client: httpx.AsyncClient, cfg: PollingConfig, method: str, payload: dict) -> dict:
    response = await client.post(_endpoint(cfg.token, method), json=payload)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict) or data.get("ok") is not True:
        raise RuntimeError("Telegram API refused request")
    return data


async def poll_batch(client: httpx.AsyncClient, redis: Redis, cfg: PollingConfig, offset: int) -> int:
    """Ack each update only after it is ignored or safely delivered.

    This means an exception prevents later offsets from being acknowledged.
    Delivery deduplication is shared with the webhook adapter, but only the
    allowlisted user can ever receive a response from this worker.
    """
    data = await _telegram_call(client, cfg, "getUpdates", {
        "offset": offset,
        "limit": 50,
        "timeout": 20,
        "allowed_updates": ["message"],
    })
    updates = data.get("result")
    if not isinstance(updates, list):
        raise RuntimeError("Malformed Telegram update collection")
    for update in updates:
        if not isinstance(update, dict):
            raise RuntimeError("Malformed Telegram update")
        update_id = update.get("update_id")
        if type(update_id) is not int or not 0 <= update_id <= 2**63 - 1:
            raise RuntimeError("Invalid Telegram update id")
        if update_id < offset:
            continue

        safe = telegram._safe_reply(update)
        if safe is not None and safe[0] == cfg.chat_id:
            key = telegram._dedup_key(update_id, cfg.secret)
            owner = secrets.token_urlsafe(24)
            claimed = await telegram._claim(cfg.redis_url, key, owner)
            if claimed:
                try:
                    await telegram._send_message(cfg.token, cfg.chat_id, safe[1], cfg.privacy_url)
                except (httpx.HTTPError, ValueError):
                    await telegram._finish(cfg.redis_url, key, owner, sent=False)
                    raise
                await telegram._finish(cfg.redis_url, key, owner, sent=True)

        # No content or user identifiers are stored or logged, only offset.
        offset = update_id + 1
        await redis.set(_redacted_key(cfg.token, "offset"), str(offset))
    return offset


_LEASE_REFRESH = """
if redis.call('GET',KEYS[1]) == ARGV[1] then
    return redis.call('EXPIRE',KEYS[1],90)
end
return 0
"""
_LEASE_RELEASE = """
if redis.call('GET',KEYS[1]) == ARGV[1] then
    return redis.call('DEL',KEYS[1])
end
return 0
"""


async def run() -> int:
    cfg = config_from_env()
    if cfg is None:
        print("FAIL: local Telegram polling is disabled or incorrectly configured", flush=True)
        return 2

    redis = Redis.from_url(cfg.redis_url, socket_connect_timeout=4, socket_timeout=4)
    lease_key = _redacted_key(cfg.token, "lease")
    lease_owner = secrets.token_urlsafe(24)
    lease_acquired = False
    try:
        await redis.ping()
        # Single-reader lease: do not allow two pollers to consume the same bot.
        lease_acquired = bool(await redis.set(lease_key, lease_owner, nx=True, ex=90))
        if not lease_acquired:
            print("FAIL: another local poller holds the Redis lease", flush=True)
            return 2
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0), follow_redirects=False) as client:
            info = await _telegram_call(client, cfg, "getWebhookInfo", {})
            if info.get("result", {}).get("url"):
                print("FAIL: webhook is active; polling will not run", flush=True)
                return 2

            stored = await redis.get(_redacted_key(cfg.token, "offset"))
            offset = int(stored) if stored is not None else 0
            print("PASS: local Telegram development poller started (allowlisted chat only)", flush=True)

            while True:
                try:
                    # After a long poll (<= 20s), 90s lease is refreshed before next poll.
                    if not await redis.eval(_LEASE_REFRESH, 1, lease_key, lease_owner):
                        print("FAIL: Telegram polling lease lost", flush=True)
                        return 2
                    offset = await poll_batch(client, redis, cfg, offset)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    # Telegram request URLs carry secrets: never echo exceptions.
                    print("WARN: polling or delivery failed; retrying safely", flush=True)
                    await asyncio.sleep(5)
    except (ConnectionError, OSError, ValueError):
        print("FAIL: Telegram polling infrastructure unavailable", flush=True)
        return 2
    finally:
        if lease_acquired:
            try:
                await redis.eval(_LEASE_RELEASE, 1, lease_key, lease_owner)
            except Exception:
                pass
        await redis.aclose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
