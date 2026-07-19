#!/usr/bin/env bash
# BotForge Postgres restore — load a gzipped pg_dump produced by backup.sh.
#
#   ./restore.sh /var/backups/botforge/botforge_botforge_20260719T031500Z.sql.gz
#
# WARNING: this restores INTO the target database. For a clean restore, drop+recreate the DB
# first (the commented block below), then run migrations are NOT needed — the dump is a full
# schema+data snapshot. Uploaded document files (UPLOAD_DIR) are backed up separately.
set -euo pipefail

DUMP="${1:?usage: restore.sh <backup.sql.gz>}"
PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-${POSTGRES_USER:-botforge}}"
PGDATABASE="${PGDATABASE:-${POSTGRES_DB:-botforge}}"
export PGPASSWORD="${PGPASSWORD:-${POSTGRES_PASSWORD:-botforge}}"

echo "[restore] restoring $DUMP -> $PGDATABASE@$PGHOST:$PGPORT"
read -r -p "This will overwrite data in '$PGDATABASE'. Continue? [y/N] " ans
[ "$ans" = "y" ] || { echo "aborted"; exit 1; }

# Optional clean slate (uncomment to drop+recreate before load):
# psql --host="$PGHOST" --port="$PGPORT" --username="$PGUSER" -d postgres \
#   -c "DROP DATABASE IF EXISTS $PGDATABASE" -c "CREATE DATABASE $PGDATABASE"

gunzip -c "$DUMP" | psql --host="$PGHOST" --port="$PGPORT" --username="$PGUSER" -d "$PGDATABASE"
echo "[restore] done. Verify: SELECT count(*) FROM organizations;"
