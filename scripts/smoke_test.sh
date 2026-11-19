#!/usr/bin/env bash
# Production smoke test. Usage: BASE_URL=https://api.example.com ./scripts/smoke_test.sh
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:5000}"
BASE_URL="${BASE_URL%/}"

echo "Checking ${BASE_URL}"
health="$(curl --fail --silent --show-error --max-time 15 "${BASE_URL}/api/health")"
printf '%s\n' "$health" | python -c 'import json,sys; data=json.load(sys.stdin)["data"]; assert data["status"] == "ok", data; assert data["database"] is True, data; print("health: ok, version", data["version"])'

curl --fail --silent --show-error --max-time 15 "${BASE_URL}/api/rules/presets" >/dev/null
echo "rules presets: ok"

curl --fail --silent --show-error --max-time 15 "${BASE_URL}/manifest.webmanifest" >/dev/null
echo "PWA manifest: ok"

status="$(curl --silent --output /dev/null --write-out '%{http_code}' --max-time 15 "${BASE_URL}/api/matches")"
if [ "$status" != "200" ] && [ "$status" != "401" ]; then
  echo "matches list unexpectedly returned HTTP ${status}" >&2
  exit 1
fi
echo "matches list: HTTP ${status} (200 unauthenticated local mode, 401 when auth is required)"

echo "Smoke test passed."
