#!/bin/sh
# Restore an encrypted database backup into TARGET_DB (default: a scratch database, never the live one).
# Usage: restore.sh /backups/db-YYYYmmddTHHMMSSZ.dump.enc [target_db]
set -eu
: "${BACKUP_PASSPHRASE:?}" "${PGHOST:?}" "${PGUSER:?}"
file="${1:?path of db-*.dump.enc}"
target="${2:-medtour_restore_check}"
if [ "$target" = "${PGDATABASE:-medtour}" ] && [ "${CONFIRM_RESTORE_OVER_LIVE:-}" != "yes" ]; then
  echo "Refusing to overwrite the live database; set CONFIRM_RESTORE_OVER_LIVE=yes to do it deliberately." >&2
  exit 1
fi
stamp=$(basename "$file" | sed -n 's/^db-\(.*\)\.dump\.enc$/\1/p')
sums="$(dirname "$file")/SHA256SUMS-$stamp"
if [ -f "$sums" ]; then (cd "$(dirname "$file")" && grep " ./$(basename "$file")\$" "$sums" | sha256sum -c -); fi
psql -v ON_ERROR_STOP=1 -d postgres -c "DROP DATABASE IF EXISTS \"$target\"" -c "CREATE DATABASE \"$target\""
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:BACKUP_PASSPHRASE -in "$file" \
  | pg_restore --no-owner --exit-on-error -d "$target"
echo "restored $file into $target"
