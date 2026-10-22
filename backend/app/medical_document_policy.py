"""Private medical-document storage policy, synthetic data only in alpha.

Storage isolation applies tenant and document UUIDs to authenticated, mapped
files. Local encryption is intentionally unscanned and cannot run in production.
The object-store adapter is external-approval gated; configuration does NOT
constitute operational certification or permission for real PHI.
"""
from __future__ import annotations

import hashlib
import os
import re
import secrets
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .secure_media import MAX_BYTES, s3_load, s3_ready, validate_file

ACTIVE_STATUSES = frozenset({"encrypted_dev_unscanned", "scanned_private_s3"})
LOCAL_BLOB_MAX = MAX_BYTES + 28  # AES-GCM 12-byte nonce + 16-byte tag


def cleaned_name(value: str | None) -> str:
    # Path on Linux will not treat Windows backslash as a separator.
    name = (value or "document").replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(c for c in name if c.isprintable() and c not in "\r\n\x00")
    name = name.strip().strip(".")
    return name[:120] or "document"


def document_path(tenant_id: str, document_id: str) -> Path:
    try:
        tenant = str(UUID(tenant_id))
        document = str(UUID(document_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(422, "Invalid private document identifier") from exc
    root = Path(os.getenv("PRIVATE_DOCUMENT_DIR", "./.private_documents")).resolve()
    parent = root / tenant
    target = parent / (document + ".enc")
    # Reject any attacker-created symbolic-link directory or file.
    if parent.is_symlink() or target.is_symlink() or not target.resolve().is_relative_to(root):
        raise HTTPException(503, "Unsafe private document path")
    return target


def encrypt_local(raw: bytes, tenant_id: str, document_id: str, cipher: AESGCM) -> Path:
    path = document_path(tenant_id, document_id)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Prevent pre-existing directory/file/symlink substitution.
    if path.parent.is_symlink() or path.is_symlink():
        raise HTTPException(503, "Unsafe private document path")
    nonce = secrets.token_bytes(12)
    encrypted = nonce + cipher.encrypt(nonce, raw, f"{tenant_id}:{document_id}".encode())
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(encrypted)
            stream.flush()
            os.fsync(stream.fileno())
    except (OSError, ValueError) as exc:
        raise HTTPException(503, "Private document write failed") from exc
    return path


def decrypt_local(tenant_id: str, document_id: str, cipher: AESGCM) -> bytes:
    path = document_path(tenant_id, document_id)
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > LOCAL_BLOB_MAX:
            raise HTTPException(404, "Private encrypted document not available")
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as stream:
            blob = stream.read(LOCAL_BLOB_MAX + 1)
    except HTTPException:
        raise
    except (OSError, ValueError) as exc:
        raise HTTPException(404, "Private encrypted document not available") from exc
    if not 29 <= len(blob) <= LOCAL_BLOB_MAX:
        raise HTTPException(500, "Encrypted document integrity failed")
    try:
        raw = cipher.decrypt(
            blob[:12], blob[12:], f"{tenant_id}:{document_id}".encode()
        )
    except Exception as exc:
        raise HTTPException(500, "Encrypted document integrity failed") from exc
    if not 0 < len(raw) <= MAX_BYTES:
        raise HTTPException(500, "Decrypted document size invalid")
    return raw


def load_document(row, tenant_id: str, *, local_enabled: bool, cipher_factory) -> tuple[bytes, str]:
    if row.status not in ACTIVE_STATUSES:
        raise HTTPException(404, "Document unavailable")
    if row.status == "scanned_private_s3":
        if not s3_ready():
            raise HTTPException(503, "Approved object storage not configured")
        raw = s3_load(row.storage_key, tenant_id, row.id, row.sha256_hex or "")
    else:
        if not local_enabled:
            raise HTTPException(503, "Development document store disabled")
        if row.storage_key != row.id + ".enc":
            raise HTTPException(500, "Invalid private storage reference")
        raw = decrypt_local(tenant_id, row.id, cipher_factory())
    mime, checksum = validate_file(raw)
    if checksum != row.sha256_hex or mime != row.mime_type or len(raw) != row.size_bytes:
        raise HTTPException(500, "Medical document integrity mismatch")
    return raw, mime


def private_download_response(raw: bytes, mime: str):
    from fastapi.responses import Response
    return Response(
        content=raw,
        media_type=mime,
        headers={
            "Cache-Control": "no-store, private",
            "Pragma": "no-cache",
            "Content-Disposition": 'attachment; filename="medical-document"',
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox",
            "Referrer-Policy": "no-referrer",
        },
    )
