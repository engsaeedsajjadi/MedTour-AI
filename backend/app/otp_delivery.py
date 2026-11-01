"""Pluggable one-time-code delivery (patient portal invitations, notifications).

OTP_DELIVERY_PROVIDER selects the channel:

* ``email``        — SMTP (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM, SMTP_STARTTLS)
* ``sms_webhook``  — POST JSON {"to","message"} to an SMS gateway adapter (OTP_SMS_WEBHOOK_URL,
                     OTP_SMS_WEBHOOK_TOKEN). Point it at a small adapter for Kavenegar, Twilio, etc.
* unset / ``none`` — no delivery; only development may then show the code to staff.

The code itself is never logged, never stored in plain text and never returned to staff when a
provider is configured.
"""
from __future__ import annotations
import json
import os
import re
import smtplib
import ssl
import urllib.request
from email.message import EmailMessage
from fastapi import HTTPException

EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[A-Za-z]{2,}$")
PHONE_RE = re.compile(r"^\+?[0-9]{8,15}$")


def provider() -> str:
    return os.getenv("OTP_DELIVERY_PROVIDER", "none").strip().lower()


def configured() -> bool:
    name = provider()
    if name == "email":
        return bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_FROM"))
    if name == "sms_webhook":
        url = os.getenv("OTP_SMS_WEBHOOK_URL", "")
        return url.startswith("https://") or (url.startswith("http://") and os.getenv("APP_ENV") != "production")
    return False


def channel_for(contact: str) -> str | None:
    value = (contact or "").strip().replace(" ", "")
    name = provider()
    if name == "email" and EMAIL_RE.fullmatch(value):
        return "email"
    if name == "sms_webhook" and PHONE_RE.fullmatch(value):
        return "sms"
    return None


def mask(contact: str) -> str:
    value = (contact or "").strip()
    if "@" in value:
        local, _, domain = value.partition("@")
        return (local[:1] or "*") + "***@" + domain
    return ("*" * max(len(value) - 3, 0)) + value[-3:]


def _send_email(to: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["From"] = os.environ["SMTP_FROM"]
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    host = os.environ["SMTP_HOST"]
    port = int(os.getenv("SMTP_PORT", "587"))
    user, password = os.getenv("SMTP_USER", ""), os.getenv("SMTP_PASSWORD", "")
    context = ssl.create_default_context()
    if port == 465:
        server = smtplib.SMTP_SSL(host, port, timeout=15, context=context)
    else:
        server = smtplib.SMTP(host, port, timeout=15)
    with server:
        if port != 465 and os.getenv("SMTP_STARTTLS", "true").lower() != "false":
            server.starttls(context=context)
        if user:
            server.login(user, password)
        server.send_message(message)


def _send_sms(to: str, body: str) -> None:
    request = urllib.request.Request(
        os.environ["OTP_SMS_WEBHOOK_URL"], method="POST",
        data=json.dumps({"to": to, "message": body}).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + os.getenv("OTP_SMS_WEBHOOK_TOKEN", "")})
    with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310 - URL is operator configured
        if response.status >= 300:
            raise OSError("SMS gateway rejected the message")


def deliver(contact: str, subject: str, body: str) -> str:
    """Send ``body`` to the patient's own contact. Returns the channel used."""
    if not configured():
        raise HTTPException(503, "Approved OTP delivery provider is not configured")
    channel = channel_for(contact)
    if channel is None:
        raise HTTPException(409, "Patient contact is not a valid address for the configured delivery channel")
    try:
        if channel == "email":
            _send_email(contact.strip(), subject, body)
        else:
            _send_sms(contact.strip().replace(" ", ""), body)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, "One-time code delivery failed; try again later") from exc
    return channel
