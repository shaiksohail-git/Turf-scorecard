#!/usr/bin/env bash
# Daily PostgreSQL backup for a single GullyScore database.
# Usage: DATABASE_URL=postgresql://... BACKUP_DIR=/var/backups/gullyscore ./scripts/backup.sh
set -euo pipefail

if [ -z "${DATABASE_URL:-}" ]; then
  echo "DATABASE_URL is required" >&2
  exit 2
fi
BACKUP_DIR="${BACKUP_DIR:-./backups}"
mkdir -p "$BACKUP_DIR"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="${BACKUP_DIR}/gullyscore-${stamp}.dump"

pg_dump --format=custom --no-owner --no-privileges --file="$target" "$DATABASE_URL"
chmod 600 "$target"
echo "Wrote $target"

# Keep 30 daily backups. Adjust retention to the deployment's policy.
find "$BACKUP_DIR" -type f -name 'gullyscore-*.dump' -mtime +30 -print -delete
