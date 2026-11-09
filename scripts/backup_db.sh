#!/usr/bin/env bash
# Backs up the Intellicart PostgreSQL database with pg_dump (custom format).
# Reads DB_* settings from backend/.env (or the environment). The password is
# passed through the environment and is never printed.
#
# Usage:        scripts/backup_db.sh
# Restore test (into a NEW database, never over the original):
#   createdb intellicart_copy
#   pg_restore --no-owner -d intellicart_copy backups/<file>.dump
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/backend/.env"

# Read one KEY=value from the env file (empty if missing).
get() { grep "^$1=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- || true; }

DB_NAME="${DB_NAME:-$(get DB_NAME)}"
DB_USER="${DB_USER:-$(get DB_USER)}"
DB_HOST="${DB_HOST:-$(get DB_HOST)}"
DB_PORT="${DB_PORT:-$(get DB_PORT)}"
export PGPASSWORD="${DB_PASSWORD:-$(get DB_PASSWORD)}"

mkdir -p "$ROOT/backups"
OUT="$ROOT/backups/${DB_NAME}_$(date +%Y%m%d_%H%M%S).dump"

# "localhost" can resolve to IPv6, which may use different login rules; prefer IPv4.
HOST="${DB_HOST:-127.0.0.1}"
[ "$HOST" = "localhost" ] && HOST=127.0.0.1

# -w: never wait for a password prompt (fail instead of hanging).
pg_dump -w -h "$HOST" -p "${DB_PORT:-5432}" -U "$DB_USER" -d "$DB_NAME" -Fc -f "$OUT"
echo "Backup written to $OUT"
