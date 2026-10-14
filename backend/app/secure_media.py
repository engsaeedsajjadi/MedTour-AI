"""Fail-closed medical document storage and malware inspection.

S3 stores private ciphertext protected by AWS KMS (SSE-KMS) in production.
ClamAV scan must return an explicit OK; scanner outages never pass a file.
No presigned public URLs or unauthenticated object downloads are issued.
"""
from __future__ import annotations
import hashlib
import os
import socket
import struct
from io import BytesIO
from fastapi import HTTPException

MAX_BYTES = 8 * 1024 * 1024
SIGNATURES = {"application/pdf": b"%PDF-", "image/png": b"\x89PNG\r\n\x1a\n", "image/jpeg": b"\xff\xd8\xff"}


def validate_file(raw: bytes) -> tuple[str,str]:
    if not raw:
        raise HTTPException(422, 'Empty document')
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, 'Document exceeds 8 MiB')
    for kind, magic in SIGNATURES.items():
        if raw.startswith(magic):
            return kind, hashlib.sha256(raw).hexdigest()
    raise HTTPException(415, 'Only PDF, JPEG and PNG contents are accepted')


def s3_ready() -> bool:
    return all([os.getenv('APP_ENV') == 'production', os.getenv('MEDICAL_S3_BUCKET'),
        os.getenv('MEDICAL_S3_KMS_KEY_ID'), os.getenv('CLAMAV_HOST'),
        os.getenv('DOCUMENT_PROCESSING_APPROVED', '').lower() == 'true'])


def scan_clamav(raw: bytes) -> None:
    host=os.environ.get('CLAMAV_HOST','')
    if not host:
        raise HTTPException(503, 'Malware scanner is not configured')
    port=int(os.getenv('CLAMAV_PORT','3310'))
    try:
        with socket.create_connection((host,port),timeout=8) as conn:
            conn.settimeout(20)
            conn.sendall(b'zINSTREAM\x00')
            for pos in range(0,len(raw),65536):
                part=raw[pos:pos+65536]
                conn.sendall(struct.pack('!I',len(part))+part)
            conn.sendall(struct.pack('!I',0))
            response=conn.recv(1024)
    except (OSError,ValueError) as exc:
        raise HTTPException(503, 'Malware scanner unavailable; upload denied') from exc
    if b'FOUND' in response:
        raise HTTPException(422, 'Malware detected; file rejected')
    if not response.strip(b'\x00\r\n ').endswith(b'OK'):
        raise HTTPException(503, 'Malware scan inconclusive; upload denied')


def s3_client():
    import boto3
    return boto3.client('s3',region_name=os.getenv('MEDICAL_S3_REGION') or None,
                        endpoint_url=os.getenv('MEDICAL_S3_ENDPOINT') or None)


def object_key(tenant_id:str,document_id:str)->str:
    # IDs are internally generated UUIDs; no original filenames in paths.
    from uuid import UUID
    return f'medical/{UUID(tenant_id)}/{UUID(document_id)}'


def s3_store(tenant_id:str,document_id:str,raw:bytes,mime:str)->str:
    if not s3_ready():
        raise HTTPException(503,'Approved S3/KMS medical storage unavailable')
    key=object_key(tenant_id,document_id)
    try:
        s3_client().put_object(Bucket=os.environ['MEDICAL_S3_BUCKET'],Key=key,Body=raw,
            ContentType=mime,ServerSideEncryption='aws:kms',
            SSEKMSKeyId=os.environ['MEDICAL_S3_KMS_KEY_ID'],
            Metadata={'integrity-sha256':hashlib.sha256(raw).hexdigest()})
    except Exception as exc:
        raise HTTPException(503,'Private object storage failed') from exc
    return key


def s3_load(key:str,tenant_id:str,document_id:str,expected_hash:str)->bytes:
    if not s3_ready() or key!=object_key(tenant_id,document_id):
        raise HTTPException(503,'Approved S3/KMS medical storage unavailable')
    try:
        result=s3_client().get_object(Bucket=os.environ['MEDICAL_S3_BUCKET'],Key=key)
        raw=result['Body'].read(MAX_BYTES+1)
    except Exception as exc:
        raise HTTPException(503,'Private document read failed') from exc
    if len(raw)>MAX_BYTES or hashlib.sha256(raw).hexdigest()!=expected_hash:
        raise HTTPException(500,'Document integrity verification failed')
    return raw
