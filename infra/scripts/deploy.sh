#!/bin/sh
# Deploys the checked-out revision on the VPS (docs/deployment.md):
#   infra/scripts/deploy.sh            # pull main, back up, build, migrate, restart, verify
#   infra/scripts/deploy.sh --no-pull  # deploy the current checkout as is
set -eu
cd "$(dirname "$0")/../.."
ENV_FILE="${ENV_FILE:-.env.production}"
COMPOSE="docker compose -f infra/docker-compose.yml --env-file $ENV_FILE"
[ -f "$ENV_FILE" ] || { echo "Missing $ENV_FILE (copy .env.production.example)"; exit 1; }

if [ "${1:-}" != "--no-pull" ]; then
  git fetch --quiet origin
  git merge --ff-only origin/main
fi
export SERTI_VERSION="$(git rev-parse --short HEAD)"
echo "Deploying $SERTI_VERSION"

$COMPOSE build --pull
# Back up before migrations touch the schema (skipped on the very first deploy).
if $COMPOSE ps --status running --services | grep -qx db; then
  $COMPOSE run --rm --entrypoint backup.sh backup
fi
$COMPOSE up -d --remove-orphans
# Report only: the first deploy fails it until the owner, 2FA and legal pages exist.
$COMPOSE exec -T backend python manage.py check_production || echo "check_production: pending items above (see docs/deployment.md)"

echo "Waiting for the site..."
i=0
until $COMPOSE exec -T backend python -c "import urllib.request as u; u.urlopen(u.Request('http://127.0.0.1:8000/api/v1/health/ready', headers={'Host': 'localhost', 'X-Forwarded-Proto': 'https'}), timeout=3)" 2>/dev/null; do
  i=$((i + 1)); [ "$i" -ge 30 ] && { echo "Backend not ready"; $COMPOSE logs --tail 50 backend; exit 1; }
  sleep 2
done
docker image prune -f >/dev/null
echo "Deployed $SERTI_VERSION"
