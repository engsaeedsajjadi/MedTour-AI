"""Synthetic tests for the explicitly allowlisted local Telegram poller."""
from __future__ import annotations

import asyncio

import httpx
from app import telegram, telegram_poller


def _env(monkeypatch):
    values = {
        "APP_ENV": "development",
        "TELEGRAM_POLLING_ENABLED": "true",
        "TELEGRAM_POLLING_TEST_MODE": "true",
        "TELEGRAM_BOT_ENABLED": "false",
        "TELEGRAM_BOT_TOKEN": "123456789:" + "T"*40,
        "TELEGRAM_WEBHOOK_SECRET": "s"*48,
        "TELEGRAM_POLLING_CHAT_ID": "12345",
        "REDIS_URL": "redis://redis:6379/0",
        "PUBLIC_PRIVACY_NOTICE_URL": "",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    return values


def test_default_denied(monkeypatch):
    _env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_POLLING_ENABLED", "false")
    assert telegram_poller.config_from_env() is None


def test_no_production_or_webhook_polling(monkeypatch):
    _env(monkeypatch)
    for key, value in (
        ("APP_ENV", "production"),
        ("TELEGRAM_POLLING_TEST_MODE", "false"),
        ("TELEGRAM_BOT_ENABLED", "true"),
        ("TELEGRAM_POLLING_CHAT_ID", ""),
        ("TELEGRAM_POLLING_CHAT_ID", "-1"),
        ("TELEGRAM_POLLING_CHAT_ID", "0"),
        ("TELEGRAM_POLLING_CHAT_ID", "999999999999999999999999"),
        ("TELEGRAM_WEBHOOK_SECRET", "too-short"),
        ("PUBLIC_PRIVACY_NOTICE_URL", "http://localhost/private"),
    ):
        monkeypatch.setenv(key, value)
        assert telegram_poller.config_from_env() is None
        _env(monkeypatch)


def test_valid_local_allowlist(monkeypatch):
    _env(monkeypatch)
    cfg = telegram_poller.config_from_env()
    assert cfg is not None and cfg.chat_id == 12345
    assert not cfg.privacy_url


class FakeRedis:
    def __init__(self):
        self.values = {}
    async def set(self, key, value):
        self.values[key] = value
        return True


class FakeHTTP:
    def __init__(self, updates):
        self.updates = updates
        self.queries = []
    async def post(self, url, json):
        assert url.endswith("/getUpdates")
        self.queries.append(json)
        return httpx.Response(
            200, request=httpx.Request("POST", url),
            json={"ok": True, "result": self.updates}
        )


def _update(update_id: int, chat_id: int, text: str):
    return {"update_id": update_id, "message": {
        "chat": {"type": "private", "id": chat_id},
        "from": {"id": chat_id, "language_code": "fa", "is_bot": False},
        "text": text,
    }}


def test_unauthorized_chat_never_replied_to(monkeypatch):
    _env(monkeypatch)
    cfg = telegram_poller.config_from_env()
    async def reject(*args):
        raise AssertionError("Unauthorized chat must not cause outbound delivery")
    monkeypatch.setattr(telegram, "_send_message", reject)
    http = FakeHTTP([_update(101, 999, "/start fa")])
    redis = FakeRedis()
    offset = asyncio.run(telegram_poller.poll_batch(http, redis, cfg, 0))
    assert offset == 102
    assert http.queries[0]["allowed_updates"] == ["message"]
    assert len(redis.values) == 1


def test_authorized_chat_generates_safe_reply_and_ack(monkeypatch):
    _env(monkeypatch)
    cfg = telegram_poller.config_from_env()
    deliveries = []
    async def claim(*args):
        return True
    async def finish(*args, **kwargs):
        assert kwargs["sent"] is True
    async def send(token, chat, text, privacy):
        deliveries.append((chat, text, privacy))
    monkeypatch.setattr(telegram, "_claim", claim)
    monkeypatch.setattr(telegram, "_finish", finish)
    monkeypatch.setattr(telegram, "_send_message", send)
    http = FakeHTTP([_update(10, 12345, "/start fa"), _update(11, 12345, "Synthetic private text 553311")])
    redis = FakeRedis()
    offset = asyncio.run(telegram_poller.poll_batch(http, redis, cfg, 0))
    assert offset == 12
    assert len(deliveries) == 2
    assert all("Synthetic private text 553311" not in reply for _, reply, _ in deliveries)
    assert all(chat == 12345 and not privacy for chat, _, privacy in deliveries)
    assert all("پاسپورت" in reply for _, reply, _ in deliveries)


def test_failed_send_is_not_acknowledged(monkeypatch):
    _env(monkeypatch)
    cfg = telegram_poller.config_from_env()
    released = []
    async def claim(*args):
        return True
    async def finish(*args, **kwargs):
        released.append(kwargs["sent"])
    async def send(*args):
        raise httpx.ConnectError("synthetic", request=httpx.Request("POST", "https://api.telegram.org"))
    monkeypatch.setattr(telegram, "_claim", claim)
    monkeypatch.setattr(telegram, "_finish", finish)
    monkeypatch.setattr(telegram, "_send_message", send)
    redis = FakeRedis()
    import pytest
    with pytest.raises(httpx.ConnectError):
        asyncio.run(telegram_poller.poll_batch(FakeHTTP([_update(5, 12345, "/start")]), redis, cfg, 0))
    assert not redis.values
    assert released == [False]


def test_no_privacy_url_does_not_invent_link(monkeypatch):
    recorded = []
    class MockClient:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, json):
            recorded.append(json)
            return httpx.Response(200, request=httpx.Request("POST", url), json={"ok": True})
    monkeypatch.setattr(telegram.httpx, "AsyncClient", MockClient)
    asyncio.run(telegram._send_message("123456789:"+"A"*40, 12345, "generic", ""))
    assert recorded[0]["text"] == "generic"
