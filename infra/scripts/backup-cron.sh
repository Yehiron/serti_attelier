#!/bin/sh
# Runs backup.sh every day at BACKUP_HOUR (America/Bogota). A failed run is retried
# the next day; the log line is what monitoring should watch.
set -u
HOUR="${BACKUP_HOUR:-3}"
export TZ=America/Bogota

while true; do
  now=$(date +%s)
  next=$(date -d "$(date +%Y-%m-%d) $HOUR:00:00" +%s 2>/dev/null || date -D '%Y-%m-%d %H:%M:%S' -d "$(date +%Y-%m-%d) $HOUR:00:00" +%s)
  [ "$next" -le "$now" ] && next=$((next + 86400))
  sleep $((next - now))
  if ! backup.sh; then
    echo "backup FAILED $(date -u +%Y%m%dT%H%M%SZ)" >&2
  fi
done
