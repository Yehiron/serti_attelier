#!/bin/sh
# Internal helper: touches only the uniquely named verification DB and /verify.
set -eu
case "${1:-}" in cleanup|--confirm-temporary-restore) ;; *) exit 2;; esac
case "${VERIFY_DB:-}" in serti_verify_[0-9]*_[0-9]*) ;; *) exit 2;; esac
[ "$VERIFY_DB" != "$POSTGRES_DB" ] || exit 2
export PGPASSWORD="$POSTGRES_PASSWORD"
HOST=${POSTGRES_HOST:-db}
if [ "${1:-}" = cleanup ]; then
  dropdb -h "$HOST" -U "$POSTGRES_USER" --if-exists "$VERIFY_DB"
  exit
fi
[ "${1:-}" = --confirm-temporary-restore ] || exit 2
cd /backups
# A checksum manifest marks a completed pair. Partial backups are never selected.
MANIFEST=$(find . -maxdepth 1 -name 'checksums-*.sha256' -type f | sort | tail -1)
[ -n "$MANIFEST" ] || { echo "No hay copias completas" >&2; exit 1; }
STAMP=${MANIFEST#./checksums-}; STAMP=${STAMP%.sha256}
case "$STAMP" in *[!0-9TZ]*|'') exit 2;; esac
sha256sum -c "$MANIFEST"
mkdir -p /verify/media /verify/private_media
age -d -i /keys/backup.key -o /verify/db.dump "db-$STAMP.dump.age"
age -d -i /keys/backup.key -o /verify/media.tar.gz "media-$STAMP.tar.gz.age"
# Reject links and paths outside the two media roots before extracting.
tar -tzf /verify/media.tar.gz | awk '
  /^\// || /(^|\/)\.\.($|\/)/ || !/^(media|private_media)(\/|$)/ { bad=1 }
  END { exit bad }'
tar -tvzf /verify/media.tar.gz | awk 'substr($0,1,1)!="-" && substr($0,1,1)!="d" {bad=1} END {exit bad}'
tar -C /verify -xzf /verify/media.tar.gz
createdb -h "$HOST" -U "$POSTGRES_USER" "$VERIFY_DB"
pg_restore -h "$HOST" -U "$POSTGRES_USER" -d "$VERIFY_DB" --no-owner --no-privileges --single-transaction /verify/db.dump
chmod -R a+rX /verify
echo "Copia restaurada en entorno temporal: $STAMP"
