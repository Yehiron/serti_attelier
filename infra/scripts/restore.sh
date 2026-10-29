#!/bin/sh
# Restores a backup produced by backup.sh (runs inside the backup container).
#   restore.sh /keys/serti-backup.key db-20261028T080000Z.dump.age [media-....tar.gz.age]
# Stop backend, worker and beat first (docs/deployment.md). The database is replaced.
set -eu

KEY="${1:?usage: restore.sh KEY_FILE DB_BACKUP [MEDIA_BACKUP]}"
DB="${2:?usage: restore.sh KEY_FILE DB_BACKUP [MEDIA_BACKUP]}"
MEDIA="${3:-}"
# Container path of the BACKUP_DIR bind mount (BACKUP_DIR itself is the host path).
DEST=/backups
case "$DB" in /*) ;; *) DB="$DEST/$DB" ;; esac
if [ -n "$MEDIA" ]; then case "$MEDIA" in /*) ;; *) MEDIA="$DEST/$MEDIA" ;; esac; fi

: "${POSTGRES_DB:?}" "${POSTGRES_USER:?}" "${POSTGRES_PASSWORD:?}"
export PGPASSWORD="$POSTGRES_PASSWORD"
HOST="${POSTGRES_HOST:-db}"

echo "Restoring database from $(basename "$DB")"
age -d -i "$KEY" "$DB" \
  | pg_restore -h "$HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
      --clean --if-exists --no-owner --no-privileges --single-transaction

if [ -n "$MEDIA" ]; then
  echo "Restoring files from $(basename "$MEDIA")"
  age -d -i "$KEY" "$MEDIA" | tar -C /srv -xzf -
fi
echo "restore ok"
