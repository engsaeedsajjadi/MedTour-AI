#!/bin/sh
# Encrypted, scheduled backups of the database and the stored medical documents.
# Every archive is AES-256 encrypted with BACKUP_PASSPHRASE before it touches the backup volume.
set -eu
: "${PGHOST:?}" "${PGUSER:?}" "${PGDATABASE:?}" "${BACKUP_PASSPHRASE:?Set BACKUP_PASSPHRASE (24+ chars) in .env}"
[ "${#BACKUP_PASSPHRASE}" -ge 24 ] || { echo "BACKUP_PASSPHRASE must contain at least 24 characters" >&2; exit 1; }
INTERVAL_HOURS="${BACKUP_INTERVAL_HOURS:-24}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
OUT=/backups
mkdir -p "$OUT"
umask 077

encrypt() { openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass env:BACKUP_PASSPHRASE; }

run_once() {
  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  tmp="$OUT/.partial-$stamp"
  mkdir -p "$tmp"
  pg_dump --format=custom --no-owner "$PGDATABASE" | encrypt > "$tmp/db-$stamp.dump.enc"
  for dir in /data/documents /data/minio; do
    if [ -d "$dir" ] && [ -n "$(ls -A "$dir" 2>/dev/null)" ]; then
      name=$(basename "$dir")
      tar -C "$dir" -cf - . | encrypt > "$tmp/$name-$stamp.tar.enc"
    fi
  done
  (cd "$tmp" && sha256sum ./*.enc > "SHA256SUMS-$stamp")
  mv "$tmp"/* "$OUT"/ && rmdir "$tmp"
  find "$OUT" -maxdepth 1 -type f -mtime +"$RETENTION_DAYS" -delete
  echo "backup $stamp complete ($(ls "$OUT"/*-"$stamp"* | wc -l) files)"
}

if [ "${1:-}" = "--once" ]; then run_once; exit 0; fi
while true; do
  run_once || echo "backup failed at $(date -u +%FT%TZ)" >&2
  sleep $((INTERVAL_HOURS * 3600))
done
