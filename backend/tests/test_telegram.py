"""Synthetic tests for Telegram onboarding gateway. No external services required."""
from __future__ import annotations

import json

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import telegram

SECRET = 'x' * 48
TOKEN = '123456789:' + 'Y' * 40
HEADERS = {'X-Telegram-Bot-Api-Secret-Token': SECRET}


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setenv('TELEGRAM_BOT_ENABLED', 'true')
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', TOKEN)
    monkeypatch.setenv('TELEGRAM_WEBHOOK_SECRET', SECRET)
    monkeypatch.setenv('PUBLIC_PRIVACY_NOTICE_URL', 'https://example.invalid/privacy')
    monkeypatch.setenv('REDIS_URL', 'redis://localhost:6379/0')
    owned = {}
    out = []

    async def claim(_url, key, owner):
        if key in owned:
            return False
        owned[key] = owner
        return True

    async def finish(_url, key, owner, *, sent):
        if owned.get(key) == owner and not sent:
            del owned[key]

    async def send(_token, chat_id, reply, privacy_url):
        out.append((chat_id, reply, privacy_url))

    monkeypatch.setattr(telegram, '_claim', claim)
    monkeypatch.setattr(telegram, '_finish', finish)
    monkeypatch.setattr(telegram, '_send_message', send)
    app = FastAPI()
    app.include_router(telegram.router)
    return TestClient(app, raise_server_exceptions=False), owned, out


def update(*, chat_type='private', text='/start fa', chat_id=1234, sender_id=1234, update_id=1, lang='en'):
    return {'update_id': update_id, 'message': {'chat': {'type': chat_type, 'id': chat_id},
        'from': {'id': sender_id, 'language_code': lang, 'is_bot': False}, 'text': text}}


def post(client, payload, headers=None):
    return client.post('/api/v1/webhooks/telegram', content=json.dumps(payload),
                       headers={**HEADERS, 'content-type':'application/json'} if headers is None else headers)


def test_disabled_by_default(monkeypatch, setup):
    client, _, out = setup
    monkeypatch.setenv('TELEGRAM_BOT_ENABLED', 'false')
    response = post(client, update())
    assert response.status_code == 503 and not out


def test_credential_validation_fail_closed(monkeypatch, setup):
    client, _, out = setup
    monkeypatch.setenv('TELEGRAM_WEBHOOK_SECRET', 'too-short')
    assert post(client, update()).status_code == 503
    assert not out


def test_webhook_secret_required_and_no_side_effect(setup):
    client, _, out = setup
    assert post(client, update(), headers={'content-type':'application/json'}).status_code == 403
    assert post(client, update(), headers={'content-type':'application/json', 'X-Telegram-Bot-Api-Secret-Token': 'z'*48}).status_code == 403
    assert not out


def test_returns_generic_persian_notice_and_minimal_response(setup):
    client, _, out = setup
    response = post(client, update(text='/start fa'))
    assert response.status_code == 200
    assert response.json() == {'ok': True, 'sent_generic_notice': True}
    assert len(out) == 1 and 'پاسپورت' in out[0][1]
    assert out[0][2] == 'https://example.invalid/privacy'


def test_replay_does_not_repeat_message(setup):
    client, _, out = setup
    assert post(client, update()).status_code == 200
    assert post(client, update()).json() == {'ok': True, 'duplicate': True}
    assert len(out) == 1


def test_ignores_groups_and_forged_sender(setup):
    client, _, out = setup
    assert post(client, update(chat_type='group')).json()['ignored'] is True
    assert post(client, update(sender_id=8888)).json()['ignored'] is True
    assert not out


def test_free_text_is_discarded_and_never_echoed(setup):
    client, _, out = setup
    sensitive = 'My private medical data / passport is: #55512345'
    response = post(client, update(text=sensitive))
    assert response.status_code == 200
    assert sensitive not in response.text
    assert sensitive not in out[0][1]
    assert 'Do not send' in out[0][1]


@pytest.mark.parametrize('language,needle', [('fa','پاسپورت'),('ar','سجلات طبية'),('en','medical records'),('ps','طبي اسناد'),('prs','اسناد طبی')])
def test_all_five_languages(setup, language, needle):
    client, _, out = setup
    assert post(client, update(text='/language ' + language)).status_code == 200
    assert needle in out[0][1]


def test_malformed_json_bad_media_type_and_large_payload(setup):
    client, _, out = setup
    url = '/api/v1/webhooks/telegram'
    assert client.post(url, content='oops',headers={**HEADERS, 'content-type':'application/json'}).status_code==400
    assert client.post(url, content='{}',headers={**HEADERS, 'content-type':'text/plain'}).status_code==415
    assert client.post(url, content='x'*65537,headers={**HEADERS, 'content-type':'application/json'}).status_code==413
    assert not out


def test_update_id_type_validation(setup):
    client, _, out = setup
    for update_id in (True, -1, 2**65, '1'):
        assert post(client, update(update_id=update_id)).status_code==422
    assert not out


def test_sender_missing_or_callback_ignored(setup):
    client, _, out = setup
    assert post(client, {'update_id':2,'callback_query':{'id':'abc'}}).json()['ignored'] is True
    assert post(client, {'update_id':3,'message':{'chat': {'type':'private','id':1}}}).json()['ignored'] is True
    assert not out


def test_upstream_failure_releases_reservation_and_returns_retryable_error(setup, monkeypatch):
    client, owned, out = setup
    async def reject(*args):
        raise httpx.ReadTimeout('synthetic')
    monkeypatch.setattr(telegram,'_send_message',reject)
    resp = post(client, update())
    assert resp.status_code == 503 and not owned and not out


def test_dedupe_outage_fails_closed_and_no_send(setup, monkeypatch):
    client, _, out = setup
    async def broken(*args):
        raise ConnectionError('synthetic redis offline')
    monkeypatch.setattr(telegram,'_claim',broken)
    resp = post(client, update())
    assert resp.status_code == 503 and not out


def test_real_http_adapter_posts_static_notice_to_api(monkeypatch):
    received = []
    class MockClient:
        def __init__(self, **kwargs):
            assert kwargs['follow_redirects'] is False
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, json):
            assert url.startswith('https://api.telegram.org/bot')
            received.append(json)
            return httpx.Response(200, json={'ok':True}, request=httpx.Request('POST',url))
    monkeypatch.setattr(telegram.httpx, 'AsyncClient', MockClient)
    import asyncio
    asyncio.run(telegram._send_message(TOKEN, 42, 'generic', 'https://example.invalid/privacy'))
    assert received == [{'chat_id':42, 'text':'generic\n\nPrivacy notice: https://example.invalid/privacy', 'disable_web_page_preview':True, 'protect_content':True}]
