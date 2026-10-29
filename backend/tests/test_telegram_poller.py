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
    async def set(self, key, value, ex=None):
        assert ex is None or ex > 0
        self.values[key] = value
        return True
    async def get(self, key):
        return self.values.get(key)


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


def _update(update_id: int, chat_id: int, text: str, lang: str = "fa"):
    return {"update_id": update_id, "message": {
        "chat": {"type": "private", "id": chat_id},
        "from": {"id": chat_id, "language_code": lang, "is_bot": False},
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


def test_selected_persian_survives_followup_with_english_telegram_ui(monkeypatch):
    _env(monkeypatch)
    cfg = telegram_poller.config_from_env()
    deliveries = []
    async def claim(*args):
        return True
    async def finish(*args, **kwargs):
        assert kwargs["sent"] is True
    async def send(token, chat, text, privacy):
        deliveries.append(text)
    monkeypatch.setattr(telegram, "_claim", claim)
    monkeypatch.setattr(telegram, "_finish", finish)
    monkeypatch.setattr(telegram, "_send_message", send)
    redis = FakeRedis()
    first = FakeHTTP([_update(101, 12345, "/start fa", "en")])
    assert asyncio.run(telegram_poller.poll_batch(first, redis, cfg, 0)) == 102
    second = FakeHTTP([_update(102, 12345, "Some safe synthetic free text", "en")])
    assert asyncio.run(telegram_poller.poll_batch(second, redis, cfg, 102)) == 103
    assert len(deliveries) == 2
    assert all("پاسپورت" in reply for reply in deliveries)
    locale_key = telegram_poller._locale_key(cfg)
    assert redis.values[locale_key] == "fa"
    assert redis.values[telegram_poller._redacted_key(cfg.token, "offset")] == "103"
    assert all("Some safe synthetic free text" not in str(v) for v in redis.values.values())


def test_farsi_greeting_when_telegram_ui_is_english(monkeypatch):
    _env(monkeypatch)
    cfg = telegram_poller.config_from_env()
    delivered = []
    async def claim(*args):
        return True
    async def finish(*args, **kwargs):
        assert kwargs["sent"] is True
    async def send(token, chat, text, privacy):
        delivered.append(text)
    monkeypatch.setattr(telegram, "_claim", claim)
    monkeypatch.setattr(telegram, "_finish", finish)
    monkeypatch.setattr(telegram, "_send_message", send)
    redis = FakeRedis()
    assert asyncio.run(telegram_poller.poll_batch(
        FakeHTTP([_update(201, 12345, "سلام", "en")]), redis, cfg, 0
    )) == 202
    assert len(delivered) == 1 and "پاسپورت" in delivered[0]
    assert redis.values[telegram_poller._locale_key(cfg)] == "fa"


def test_explicit_language_switch_and_unauthorized_chat_isolation(monkeypatch):
    _env(monkeypatch)
    cfg = telegram_poller.config_from_env()
    delivered = []
    async def claim(*args):
        return True
    async def finish(*args, **kwargs):
        assert kwargs["sent"] is True
    async def send(token, chat, text, privacy):
        delivered.append(text)
    monkeypatch.setattr(telegram, "_claim", claim)
    monkeypatch.setattr(telegram, "_finish", finish)
    monkeypatch.setattr(telegram, "_send_message", send)
    redis = FakeRedis()
    updates = [
        _update(301, 99999, "/language ar", "fa"),
        _update(302, 12345, "/language fa", "en"),
        _update(303, 12345, "/language ar", "en"),
        _update(304, 12345, "hello", "en"),
    ]
    assert asyncio.run(telegram_poller.poll_batch(FakeHTTP(updates), redis, cfg, 0)) == 305
    assert len(delivered) == 3
    assert "پاسپورت" in delivered[0]
    assert all("سجلات طبية" in text for text in delivered[1:])
    assert redis.values[telegram_poller._locale_key(cfg)] == "ar"
    assert all("99999" not in str(key) for key in redis.values)
    assert all("hello" not in str(value) for value in redis.values.values())


def test_invalid_language_command_does_not_replace_preference(monkeypatch):
    _env(monkeypatch)
    cfg = telegram_poller.config_from_env()
    delivered = []
    async def claim(*args):
        return True
    async def finish(*args, **kwargs):
        pass
    async def send(token, chat, text, privacy):
        delivered.append(text)
    monkeypatch.setattr(telegram, "_claim", claim)
    monkeypatch.setattr(telegram, "_finish", finish)
    monkeypatch.setattr(telegram, "_send_message", send)
    redis = FakeRedis()
    assert asyncio.run(telegram_poller.poll_batch(
        FakeHTTP([_update(401, 12345, "/start fa", "en"),
                  _update(402, 12345, "/language xx", "en")]), redis, cfg, 0
    )) == 403
    assert redis.values[telegram_poller._locale_key(cfg)] == "fa"
    assert "پاسپورت" in delivered[-1]


def test_language_preference_uses_hmac_scoped_to_allowlisted_chat(monkeypatch):
    _env(monkeypatch)
    cfg = telegram_poller.config_from_env()
    assert str(cfg.chat_id) not in telegram_poller._locale_key(cfg)
    assert cfg.secret not in telegram_poller._locale_key(cfg)
    assert cfg.token not in telegram_poller._locale_key(cfg)


def test_safe_error_codes_never_expose_telegram_token():
    token = "123456789:" + "X" * 40
    request = httpx.Request("POST", "https://api.telegram.org/bot" + token + "/getUpdates")
    for error, expected in (
        (httpx.ConnectTimeout("sensitive " + token, request=request), "telegram_connect_timeout"),
        (httpx.ReadTimeout("sensitive " + token, request=request), "telegram_read_timeout"),
        (httpx.ConnectError("sensitive " + token, request=request), "telegram_connect_error"),
    ):
        code = telegram_poller._safe_failure_code(error)
        assert code == expected and token not in code
    for status, expected, fatal in (
        (429, "telegram_rate_limited", False),
        (500, "telegram_server_error", False),
        (401, "telegram_authorization_failed", True),
        (409, "telegram_conflicting_receiver", True),
    ):
        response = httpx.Response(status, request=request)
        error = httpx.HTTPStatusError("sensitive " + token, request=request, response=response)
        assert telegram_poller._safe_failure_code(error) == expected
        assert telegram_poller._fatal_telegram_error(error) is fatal


def test_bounded_exponential_backoff():
    assert telegram_poller._backoff_seconds(1, jitter=0) == 2.0
    assert telegram_poller._backoff_seconds(2, jitter=0) == 4.0
    assert telegram_poller._backoff_seconds(3, jitter=0.5) == 8.5
    assert telegram_poller._backoff_seconds(100, jitter=1) == 20.0


def test_local_poller_recovers_after_connect_timeout(monkeypatch, capsys):
    import pytest

    _env(monkeypatch)
    requests = []

    class WorkerRedis:
        async def ping(self): return True
        async def set(self, *args, **kwargs): return True
        async def get(self, *args): return None
        async def eval(self, script, *args): return 1
        async def aclose(self): pass

    class FlakyClient:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, json):
            requests.append(url)
            if len(requests) == 1:
                raise httpx.ConnectTimeout("secret test", request=httpx.Request("POST", url))
            return httpx.Response(
                200, request=httpx.Request("POST", url),
                json={"ok": True, "result": {"url": ""}}
            )

    async def cancel_after_recovery(*args):
        raise asyncio.CancelledError()

    async def no_sleep(*args):
        return None

    monkeypatch.setattr(telegram_poller.Redis, "from_url", lambda *args, **kwargs: WorkerRedis())
    monkeypatch.setattr(telegram_poller.httpx, "AsyncClient", FlakyClient)
    monkeypatch.setattr(telegram_poller, "poll_batch", cancel_after_recovery)
    monkeypatch.setattr(telegram_poller.asyncio, "sleep", no_sleep)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(telegram_poller.run())
    log = capsys.readouterr().out
    assert "WARN: telegram_connect_timeout; retry with backoff" in log
    assert "PASS: local Telegram development poller started" in log
    assert "123456789:" not in log
    assert len(requests) == 2


def test_local_poller_exits_on_invalid_bot_credentials(monkeypatch, capsys):
    _env(monkeypatch)

    class WorkerRedis:
        async def ping(self): return True
        async def set(self, *args, **kwargs): return True
        async def get(self, *args): return None
        async def eval(self, script, *args): return 1
        async def aclose(self): pass

    class DeniedClient:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, json):
            return httpx.Response(401, request=httpx.Request("POST", url))

    monkeypatch.setattr(telegram_poller.Redis, "from_url", lambda *args, **kwargs: WorkerRedis())
    monkeypatch.setattr(telegram_poller.httpx, "AsyncClient", DeniedClient)
    assert asyncio.run(telegram_poller.run()) == 2
    output = capsys.readouterr().out
    assert "FAIL: telegram_authorization_failed; polling stopped" in output
    assert "123456789:" not in output
