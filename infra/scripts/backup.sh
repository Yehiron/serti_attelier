#!/bin/sh
# Encrypted backup of the database and uploaded files (runs inside the backup container).
# Encrypts to BACKUP_AGE_RECIPIENT (an age public key); the matching private key never
# lives on the server, so a compromised VPS cannot read old backups.
set -eu

: "${BACKUP_AGE_RECIPIENT:?BACKUP_AGE_RECIPIENT is required}"
: "${POSTGRES_DB:?}" "${POSTGRES_USER:?}" "${POSTGRES_PASSWORD:?}"
# Container path of the BACKUP_DIR bind mount (BACKUP_DIR itself is the host path).
DEST=/backups
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
umask 077
mkdir -p "$DEST"

export PGPASSWORD="$POSTGRES_PASSWORD"
DB_FILE="$DEST/db-$STAMP.dump.age"
MEDIA_FILE="$DEST/media-$STAMP.tar.gz.age"

pg_dump -h "${POSTGRES_HOST:-db}" -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  --format=custom --no-owner --no-privileges \
  | age -r "$BACKUP_AGE_RECIPIENT" -o "$DB_FILE.partial"
mv "$DB_FILE.partial" "$DB_FILE"

tar -C /srv -czf - media private_media \
  | age -r "$BACKUP_AGE_RECIPIENT" -o "$MEDIA_FILE.partial"
mv "$MEDIA_FILE.partial" "$MEDIA_FILE"

(cd "$DEST" && sha256sum "$(basename "$DB_FILE")" "$(basename "$MEDIA_FILE")" > "checksums-$STAMP.sha256")

find "$DEST" -maxdepth 1 -type f \( -name 'db-*' -o -name 'media-*' -o -name 'checksums-*' \) \
  -mtime "+$RETENTION_DAYS" -delete
rm -f "$DEST"/*.partial

echo "backup ok $STAMP db=$(du -h "$DB_FILE" | cut -f1) media=$(du -h "$MEDIA_FILE" | cut -f1)"
