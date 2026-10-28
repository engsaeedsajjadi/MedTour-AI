"""Development-only, allowlisted Telegram long-polling worker.

The worker never creates patient records, stores message content, accesses the
clinical database, or treats Telegram as a secure patient portal. It is
deliberately NOT a production-ready bot deployment.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
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


def _safe_failure_code(error: Exception) -> str:
    """Never log exception text or a Telegram URL containing the bot token."""
    if isinstance(error, httpx.ConnectTimeout):
        return "telegram_connect_timeout"
    if isinstance(error, httpx.ReadTimeout):
        return "telegram_read_timeout"
    if isinstance(error, httpx.ConnectError):
        return "telegram_connect_error"
    if isinstance(error, httpx.TimeoutException):
        return "telegram_other_timeout"
    if isinstance(error, httpx.HTTPStatusError):
        code = error.response.status_code
        if code == 429:
            return "telegram_rate_limited"
        if code == 409:
            return "telegram_conflicting_receiver"
        if code in (401, 403):
            return "telegram_authorization_failed"
        if 500 <= code <= 599:
            return "telegram_server_error"
        return "telegram_unexpected_http_status"
    if isinstance(error, httpx.HTTPError):
        return "telegram_transport_error"
    if isinstance(error, OSError):
        return "network_or_redis_error"
    return "polling_internal_error"


def _fatal_telegram_error(error: Exception) -> bool:
    """Do not retry endlessly with invalid credentials or another receiver."""
    return (
        isinstance(error, httpx.HTTPStatusError)
        and error.response.status_code in (401, 403, 409)
    )


def _backoff_seconds(failures: int, *, jitter: float = 0.0) -> float:
    """Bounded exponential delay; no busy-looping during Telegram outages."""
    return min(20.0, float(2 ** min(max(failures, 1), 5)) + min(max(jitter, 0.0), 1.0))


def _endpoint(token: str, method: str) -> str:
    return "https://api.telegram.org/bot" + token + "/" + method


def _redacted_key(token: str, kind: str) -> str:
    return "medtour:telegram:dev-poller:" + kind + ":" + hashlib.sha256(token.encode("ascii")).hexdigest()




_LOCALE_TTL_SECONDS = 30 * 24 * 60 * 60


def _locale_key(cfg: PollingConfig) -> str:
    """Redis key has no raw chat id or token; preference is only a language code."""
    digest = hmac.new(cfg.secret.encode("ascii"), str(cfg.chat_id).encode("ascii"), hashlib.sha256).hexdigest()
    return "medtour:telegram:dev-poller:locale:" + digest


def _requested_locale(update: dict) -> str | None:
    """Only explicitly supported Telegram commands can change a chosen language."""
    message = update.get("message")
    if not isinstance(message, dict):
        return None
    raw = message.get("text")
    if not isinstance(raw, str) or len(raw) > 128:
        return None
    parts = raw.split(maxsplit=1)
    if len(parts) != 2 or parts[0].split("@", 1)[0].lower() not in ("/start", "/language", "/lang"):
        return None
    candidate = parts[1].strip().lower()
    return candidate if candidate in telegram._LANGS else None


def _greeting_locale(update: dict) -> str | None:
    """Conservative greeting-only hint; no free-text content is persisted."""
    message = update.get("message")
    if not isinstance(message, dict):
        return None
    raw = message.get("text")
    if not isinstance(raw, str) or len(raw) > 64:
        return None
    greeting = raw.strip().lower()
    if greeting in ("سلام", "درود"):
        # The greeting is shared by Persian and Arabic. Respect Arabic UI.
        return "ar" if telegram._language(message) == "ar" else "fa"
    if greeting in ("مرحبا", "أهلا", "أهلاً"):
        return "ar"
    if greeting in ("hi", "hello"):
        return "en"
    if greeting == "سلامونه":
        return "ps"
    return None


def _with_locale(update: dict, locale: str) -> dict:
    """Copy only the necessary message metadata; never mutate Telegram update."""
    message = update["message"]
    sender = message["from"]
    return {
        **update,
        "message": {**message, "from": {**sender, "language_code": locale}},
    }

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
        "limit": 2,
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
            locale_key = _locale_key(cfg)
            saved = await redis.get(locale_key)
            saved_locale = saved.decode("ascii") if isinstance(saved, bytes) else saved
            if saved_locale not in telegram._LANGS:
                saved_locale = None
            explicit = _requested_locale(update)
            greeting = _greeting_locale(update) if saved_locale is None else None
            selected = explicit or saved_locale or greeting
            localized = _with_locale(update, selected) if selected else update
            safe = telegram._safe_reply(localized)
            key = telegram._dedup_key(update_id, cfg.secret)
            owner = secrets.token_urlsafe(24)
            claimed = await telegram._claim(cfg.redis_url, key, owner)
            if claimed:
                # Store just a small locale code, not message text or patient data.
                # Write before delivery so a Redis failure cannot cause a sent
                # message with an unacknowledged language selection.
                if (explicit or greeting) and (explicit or greeting) != saved_locale:
                    try:
                        await redis.set(locale_key, explicit or greeting, ex=_LOCALE_TTL_SECONDS)
                    except Exception:
                        await telegram._finish(cfg.redis_url, key, owner, sent=False)
                        raise
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
        # getUpdates uses a 20s long poll; a read timeout must be longer.
        # Longer connect budget tolerates the intermittent Docker->Telegram timeouts.
        timeout = httpx.Timeout(connect=18.0, read=35.0, write=12.0, pool=8.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            stored = await redis.get(_redacted_key(cfg.token, "offset"))
            offset = int(stored) if stored is not None else 0
            verified_webhook = False
            failures = 0
            print("INFO: local Telegram poller starting; checking API connectivity", flush=True)
            while True:
                try:
                    # Refresh singleton lease even while reconnecting; do not allow
                    # concurrent pollers when connectivity is intermittent.
                    if not await redis.eval(_LEASE_REFRESH, 1, lease_key, lease_owner):
                        print("FAIL: Telegram polling lease lost", flush=True)
                        return 2
                    if not verified_webhook:
                        info = await _telegram_call(client, cfg, "getWebhookInfo", {})
                        if info.get("result", {}).get("url"):
                            print("FAIL: webhook is active; polling will not run", flush=True)
                            return 2
                        verified_webhook = True
                        print("PASS: local Telegram development poller started (allowlisted chat only)", flush=True)
                    offset = await poll_batch(client, redis, cfg, offset)
                    if failures:
                        print("PASS: Telegram API connection recovered", flush=True)
                    failures = 0
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    # Never print exception text; it may include a bot token URL.
                    reason = _safe_failure_code(error)
                    if _fatal_telegram_error(error):
                        print("FAIL: " + reason + "; polling stopped", flush=True)
                        return 2
                    failures += 1
                    wait = _backoff_seconds(failures, jitter=secrets.randbelow(1000) / 1000.0)
                    print("WARN: " + reason + "; retry with backoff", flush=True)
                    await asyncio.sleep(wait)
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
