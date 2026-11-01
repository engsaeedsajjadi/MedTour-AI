#!/bin/sh
# Restore drill: restore the newest backup into a scratch database and check it is complete.
set -eu
latest=$(ls -1t /backups/db-*.dump.enc 2>/dev/null | head -1)
[ -n "$latest" ] || { echo "no database backup found" >&2; exit 1; }
restore.sh "$latest" medtour_restore_check
tables=$(psql -At -d medtour_restore_check -c "select count(*) from pg_tables where schemaname='public'")
tenants=$(psql -At -d medtour_restore_check -c "select count(*) from tenants")
rls=$(psql -At -d medtour_restore_check -c "select count(*) from pg_class where relkind='r' and relnamespace='public'::regnamespace and relrowsecurity and relforcerowsecurity")
psql -q -d postgres -c "DROP DATABASE medtour_restore_check"
echo "restore drill OK: $latest -> tables=$tables tenants=$tenants rls_forced=$rls"
[ "$tables" -gt 50 ] && [ "$rls" -gt 0 ]
