#!/usr/bin/env bash
# BotForge Postgres backup — pg_dump to a timestamped, compressed file, with rotation.
#
# Cron example (daily 03:15, keep 14 days):
#   15 3 * * *  BACKUP_DIR=/var/backups/botforge RETENTION_DAYS=14 /opt/botforge/infra/scripts/backup.sh
#
# In Docker, run it from a container that can reach postgres, e.g.:
#   docker compose exec -T postgres sh -c 'PGPASSWORD=$POSTGRES_PASSWORD pg_dump ...'
# or point PGHOST/PGUSER/... at the DB from the host.
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-${POSTGRES_USER:-botforge}}"
PGDATABASE="${PGDATABASE:-${POSTGRES_DB:-botforge}}"
export PGPASSWORD="${PGPASSWORD:-${POSTGRES_PASSWORD:-botforge}}"

mkdir -p "$BACKUP_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$BACKUP_DIR/botforge_${PGDATABASE}_${STAMP}.sql.gz"

echo "[backup] pg_dump $PGDATABASE@$PGHOST:$PGPORT -> $OUT"
# Custom-format-free plain SQL, gzipped — restore with restore.sh.
pg_dump --host="$PGHOST" --port="$PGPORT" --username="$PGUSER" \
        --no-owner --no-privileges "$PGDATABASE" | gzip -9 > "$OUT"

echo "[backup] wrote $(du -h "$OUT" | cut -f1)"

# Rotate: delete backups older than RETENTION_DAYS.
find "$BACKUP_DIR" -name 'botforge_*.sql.gz' -type f -mtime "+${RETENTION_DAYS}" -print -delete || true
echo "[backup] done; retention ${RETENTION_DAYS}d"
