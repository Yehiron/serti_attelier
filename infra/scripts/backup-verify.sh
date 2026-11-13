#!/bin/sh
# Run from repository root. Only the temporary DB/volume are removed by the trap.
set -eu
[ "${1:-}" = --confirm-temporary-restore ] || { echo "Uso: $0 --confirm-temporary-restore /ruta/absoluta/backup.key [dev|prod]" >&2; exit 2; }
KEY=${2:?Falta la llave privada}
case "$KEY" in /*) ;; *) echo "La llave debe tener ruta absoluta" >&2; exit 2;; esac
[ -f "$KEY" ] || exit 2
MODE=${3:-dev}
case "$MODE" in
  dev) COMPOSE_FILE=infra/docker-compose.dev.yml; ENV_FILE=.env ;;
  prod) COMPOSE_FILE=infra/docker-compose.yml; ENV_FILE=.env.production ;;
  *) exit 2;;
esac
VERIFY_DB=serti_verify_$(date -u +%Y%m%d%H%M%S)_$$
VERIFY_VOLUME=$VERIFY_DB
compose() { docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"; }
cleanup() {
  compose run --rm --no-deps -e VERIFY_DB="$VERIFY_DB" --entrypoint backup-verify-restore.sh backup cleanup || true
  docker volume rm "$VERIFY_VOLUME" >/dev/null || true
}
docker volume create "$VERIFY_VOLUME" >/dev/null
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' HUP TERM
compose run --rm --no-deps -e VERIFY_DB="$VERIFY_DB" -v "$KEY:/keys/backup.key:ro" -v "$VERIFY_VOLUME:/verify" --entrypoint backup-verify-restore.sh backup --confirm-temporary-restore
compose run --rm --no-deps -v "$VERIFY_VOLUME:/verify:ro" --entrypoint python backend manage.py verify_backup --database-name "$VERIFY_DB" --media-root /verify/media --private-media-root /verify/private_media
