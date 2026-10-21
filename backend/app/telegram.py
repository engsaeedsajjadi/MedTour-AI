"""Minimal, privacy-preserving Telegram Bot API onboarding transport.

Opt-in only. This gateway intentionally does not create patients/cases, accept
medical files, persist message contents, call an AI model or assert consent.
Only generic multilingual notices are sent. No Telegram conversation should
be treated as the authenticated secure patient portal.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/v1/webhooks/telegram", tags=["Telegram onboarding"])

_SECRET = re.compile(r"[A-Za-z0-9_-]{32,256}\Z")
_BOT_TOKEN = re.compile(r"[0-9]{6,12}:[A-Za-z0-9_-]{35,}\Z")
_LANGS = frozenset({"fa", "ar", "en", "ps", "prs"})
_UPDATE_LIMIT = 65536

_NOTICE = {
    "fa": ("به MedTour AI خوش آمدید. این ربات فقط برای راهنمایی عمومی است. "
           "اطلاعات پزشکی، پاسپورت یا عکس مدارک را در تلگرام ارسال نکنید. "
           "برای ثبت درخواست و ارائه رضایت، از اپراتور لینک خصوصی پرتال امن بخواهید. "
           "این سرویس اورژانس یا مشاوره پزشکی نیست."),
    "ar": ("مرحبًا بك في MedTour AI. هذه القناة للمعلومات العامة فقط. "
           "لا ترسل سجلات طبية أو صور جواز السفر أو المستندات هنا. "
           "اطلب من الموظف رابطًا خاصًا للبوابة الآمنة والموافقة. "
           "هذه ليست خدمة طوارئ أو استشارة طبية."),
    "en": ("Welcome to MedTour AI. This bot provides general information only. "
           "Do not send medical records, passport photos, or private documents here. "
           "Ask an operator for a private secure-portal invitation and consent process. "
           "This is not emergency care or medical advice."),
    "ps": ("MedTour AI ته ښه راغلاست. دا روباټ یوازې عمومي لارښوونې ورکوي. "
           "طبي اسناد، پاسپورټ او شخصي عکسونه دلته مه لېږئ. "
           "له کارکوونکي څخه د خوندي پورټل شخصي لینک وغواړئ. "
           "دا د بیړني طبي مرستې خدمت نه دی."),
    "prs": ("به MedTour AI خوش آمدید. این ربات صرفاً معلومات عمومی ارائه می‌کند. "
            "اسناد طبی، پاسپورت و عکس‌های خصوصی را در تلگرام ارسال نکنید. "
            "از کارمند لینک خصوصی پورتال مصون و روند رضایت را بخواهید. "
            "این خدمات عاجل طبی نیست."),
}


@dataclass(frozen=True)
class TelegramSettings:
    token: str
    webhook_secret: str
    privacy_url: str
    redis_url: str


def settings() -> TelegramSettings | None:
    if os.getenv("TELEGRAM_BOT_ENABLED", "false").lower() != "true":
        return None
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
    privacy_url = os.getenv("PUBLIC_PRIVACY_NOTICE_URL", "")
    redis_url = os.getenv("REDIS_URL", "")
    parsed = urlsplit(privacy_url)
    if (
        not _BOT_TOKEN.fullmatch(token)
        or not _SECRET.fullmatch(secret)
        or parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or not redis_url.startswith(("redis://", "rediss://"))
    ):
        return None
    return TelegramSettings(token, secret, privacy_url, redis_url)


def enabled() -> bool:
    return settings() is not None


def _language(message: dict) -> str:
    raw = message.get("from", {}).get("language_code", "en")
    if not isinstance(raw, str):
        return "en"
    locale = raw.lower().replace("_", "-")
    if locale == "prs" or locale.startswith("prs-"):
        return "prs"
    base = locale.split("-", 1)[0]
    return base if base in _LANGS else "en"


def _safe_reply(update: dict) -> tuple[int, str] | None:
    """Return only (private chat id, generic notice); never inspect patient details."""
    message = update.get("message")
    if not isinstance(message, dict):
        return None
    chat = message.get("chat")
    sender = message.get("from")
    if not isinstance(chat, dict) or not isinstance(sender, dict):
        return None
    chat_id = chat.get("id")
    if (chat.get("type") != "private" or type(chat_id) is not int
        or chat_id <= 0 or type(sender.get("id")) is not int
        or sender["id"] != chat_id or sender.get("is_bot") is True):
        return None

    language = _language(message)
    text = message.get("text")
    if isinstance(text, str) and len(text) <= 128 and text.startswith("/"):
        words = text.split(maxsplit=1)
        command = words[0].split("@", 1)[0].lower()
        if command in {"/start", "/language", "/lang"} and len(words) > 1:
            candidate = words[1].strip().lower()
            if candidate in _LANGS:
                language = candidate
        elif command not in {"/start", "/language", "/lang", "/help", "/privacy"}:
            return None
    # Medical/free-form input is discarded; same generic warning only.
    return chat_id, _NOTICE[language]


def _dedup_key(update_id: int, key: str) -> str:
    digest = hmac.new(key.encode("ascii"), str(update_id).encode("ascii"), hashlib.sha256).hexdigest()
    return "medtour:telegram:update:" + digest


async def _claim(redis_url: str, key: str, owner: str) -> bool:
    from redis.asyncio import Redis
    client = Redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)
    try:
        return bool(await client.set(key, owner, ex=120, nx=True))
    finally:
        await client.aclose()


async def _finish(redis_url: str, key: str, owner: str, *, sent: bool) -> None:
    from redis.asyncio import Redis
    client = Redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)
    script = """
        if redis.call('GET',KEYS[1]) == ARGV[1] then
            if ARGV[2] == '1' then return redis.call('EXPIRE',KEYS[1],86400)
            else return redis.call('DEL',KEYS[1]) end
        end
        return 0
    """
    try:
        await client.eval(script, 1, key, owner, "1" if sent else "0")
    finally:
        await client.aclose()


async def _send_message(token: str, chat_id: int, reply: str, privacy_url: str) -> None:
    payload = {
        "chat_id": chat_id,
        "text": reply + "\n\nPrivacy notice: " + privacy_url,
        "disable_web_page_preview": True,
        "protect_content": True,
    }
    # No untrusted destination. Token is operator-provisioned. Never log URLs.
    async with httpx.AsyncClient(timeout=8.0, follow_redirects=False) as client:
        response = await client.post(
            "https://api.telegram.org/bot" + token + "/sendMessage", json=payload
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict) or data.get("ok") is not True:
            raise ValueError("Telegram did not accept the generic response")


@router.post("")
async def telegram_webhook(request: Request):
    config = settings()
    if config is None:
        raise HTTPException(503, "Telegram onboarding disabled or not configured")
    presented = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not isinstance(presented, str) or not hmac.compare_digest(presented, config.webhook_secret):
        raise HTTPException(403, "Invalid webhook authentication")
    raw = await request.body()
    if len(raw) > _UPDATE_LIMIT:
        raise HTTPException(413, "Telegram update exceeds allowed size")
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        raise HTTPException(415, "JSON required")
    try:
        update = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, "Invalid JSON") from None
    if not isinstance(update, dict) or type(update.get("update_id")) is not int:
        raise HTTPException(422, "Invalid update structure")
    update_id = update["update_id"]
    if not 0 <= update_id <= 2**63 - 1:
        raise HTTPException(422, "Invalid update identifier")

    reply = _safe_reply(update)
    if reply is None:
        return {"ok": True, "ignored": True}
    key = _dedup_key(update_id, config.webhook_secret)
    owner = secrets.token_urlsafe(24)
    try:
        reserved = await _claim(config.redis_url, key, owner)
    except Exception:
        raise HTTPException(503, "Telegram replay protection unavailable") from None
    if not reserved:
        return {"ok": True, "duplicate": True}
    try:
        await _send_message(config.token, reply[0], reply[1], config.privacy_url)
    except (httpx.HTTPError, ValueError):
        try:
            await _finish(config.redis_url, key, owner, sent=False)
        except Exception:
            pass  # TTL clears the abandoned reservation. No PHI is stored.
        raise HTTPException(503, "Telegram delivery failed; retry later") from None
    try:
        await _finish(config.redis_url, key, owner, sent=True)
    except Exception:
        # Delivery may have completed; never repeat the send locally.
        raise HTTPException(503, "Telegram delivery state could not be confirmed") from None
    return {"ok": True, "sent_generic_notice": True}
