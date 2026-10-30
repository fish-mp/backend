#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

deploy=/home/desai/deploy
backend=/home/desai/backend
frontend=/home/desai/frontend
exec 9>/run/lock/fishkids-deploy.lock
flock -n 9 || exit 0
compose() { docker-compose -p deploy -f "$deploy/docker-compose.yaml" "$@"; }

git -C "$backend" fetch origin master
git -C "$frontend" fetch origin main
back_sha=$(git -C "$backend" rev-parse origin/master)
front_sha=$(git -C "$frontend" rev-parse origin/main)
if [[ -f "$deploy/current-revisions" && "$(cat "$deploy/current-revisions")" == "$back_sha $front_sha" ]]; then
  echo "Already deployed $back_sha $front_sha"
  exit 0
fi

# Source changes must be committed; deployment never discards local edits.
[[ -z "$(git -C "$backend" status --porcelain --untracked-files=no)" ]]
[[ -z "$(git -C "$frontend" status --porcelain --untracked-files=no)" ]]
python3 - "$back_sha" "$front_sha" <<'PY'
import json,sys,urllib.request
for repo,sha,job in [('backend',sys.argv[1],'test'),('frontend',sys.argv[2],'build')]:
    req=urllib.request.Request(f'https://api.github.com/repos/fish-mp/{repo}/commits/{sha}/check-runs',
        headers={'Accept':'application/vnd.github+json','User-Agent':'FishKids-deploy'})
    with urllib.request.urlopen(req,timeout=20) as response:
        checks=json.load(response)['check_runs']
    matches=[c for c in checks if c['name']==job]
    if not matches or matches[0]['status']!='completed' or matches[0]['conclusion']!='success':
        raise SystemExit(f'{repo}: successful {job} CI required; deployment skipped')
PY

release="$deploy/releases/update-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$release/backend" "$release/frontend"
git -C "$backend" archive "$back_sha" | tar -x -C "$release/backend"
git -C "$frontend" archive "$front_sha" | tar -x -C "$release/frontend"
for file in robots.txt sitemap.xml; do
  if [[ -f "$frontend/public/$file" && ! -f "$release/frontend/public/$file" ]]; then
    cp "$frontend/public/$file" "$release/frontend/public/$file"
  fi
done
printf '{"revision":"%s","fishSpecies":29}\n' "$front_sha" > "$release/frontend/public/aquarium-release.json"
chmod 644 "$release/frontend/public/aquarium-release.json"

# Only public build-time variables are exported to the frontend build.
set -a
. "$frontend/.env"
set +a
override="$release/build.yaml"
printf 'version: "3.8"\nservices:\n  backend:\n    build:\n      context: %s/backend\n  frontend:\n    build:\n      context: %s/frontend\n' "$release" "$release" > "$override"
build_compose() { docker-compose -p deploy -f "$deploy/docker-compose.yaml" -f "$override" "$@"; }
build_compose build backend frontend
build_compose run --rm --no-deps --entrypoint python backend manage.py check
docker exec deploy_nginx_1 nginx -t

# Candidate images are built and checked before the running backend is stopped.
# The SQLite file is kept in place and no database backup is made by this script.
compose stop backend
git -C "$backend" merge --ff-only "$back_sha"
git -C "$frontend" merge --ff-only "$front_sha"
cat "$backend/deployment/nginx.conf" > "$deploy/nginx.conf"
docker exec deploy_nginx_1 nginx -t
build_compose run --rm --no-deps --entrypoint python backend manage.py migrate --noinput
build_compose run --rm --no-deps --entrypoint python backend manage.py collectstatic --noinput
compose up -d --no-deps --no-build backend frontend
for attempt in $(seq 1 30); do
  if curl --fail --silent --max-time 3 -H 'Host: fishkids.ru' http://127.0.0.1:8000/api/schools/ >/dev/null &&
     curl --fail --silent --max-time 3 http://127.0.0.1:5173/healthz >/dev/null; then
    break
  fi
  [[ "$attempt" != 30 ]] || { echo 'Health check failed'; exit 1; }
  sleep 2
done
docker exec deploy_nginx_1 nginx -s reload
for domain in fishkids.ru www.fishkids.ru inco-edu.ru www.inco-edu.ru; do
  curl --fail --silent --max-time 10 "https://$domain/api/schools/" >/dev/null
done
printf '%s %s\n' "$back_sha" "$front_sha" > "$deploy/current-revisions"
echo "Deployed $back_sha $front_sha"
