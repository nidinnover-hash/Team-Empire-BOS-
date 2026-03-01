#!/usr/bin/env bash
# Restore database from a backup produced by deploy/deploy.sh.
#
# Usage:
#   bash restore-db.sh --yes /opt/nidin-bos/Data/backups/postgres_predeploy_YYYYmmdd_HHMMSS.sql /opt/nidin-bos/.env
#   bash restore-db.sh --yes /opt/nidin-bos/Data/backups/postgres_predeploy_YYYYmmdd_HHMMSS.sql.gz /opt/nidin-bos/.env
#   bash restore-db.sh --yes /opt/nidin-bos/Data/backups/sqlite_predeploy_YYYYmmdd_HHMMSS.db /opt/nidin-bos/.env
set -euo pipefail

CONFIRM=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --yes)
            CONFIRM=true
            shift
            ;;
        --help|-h)
            echo "Usage: bash restore-db.sh --yes BACKUP_FILE [ENV_FILE]"
            exit 0
            ;;
        *)
            break
            ;;
    esac
done

BACKUP_FILE="${1:-}"
ENV_FILE="${2:-/opt/nidin-bos/.env}"

if [[ -z "$BACKUP_FILE" ]]; then
    echo "ERROR: BACKUP_FILE is required."
    echo "Usage: bash restore-db.sh --yes BACKUP_FILE [ENV_FILE]"
    exit 1
fi
if [[ ! -f "$BACKUP_FILE" ]]; then
    echo "ERROR: backup file not found: $BACKUP_FILE"
    exit 1
fi
if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: env file not found: $ENV_FILE"
    exit 1
fi
if ! $CONFIRM; then
    echo "ERROR: restore is destructive. Re-run with --yes."
    exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

DB_URL="${DATABASE_URL:-}"
if [[ -z "$DB_URL" ]]; then
    echo "ERROR: DATABASE_URL missing in $ENV_FILE"
    exit 1
fi

normalize_pg_url() {
    echo "$1" | sed -E 's#^postgresql\+asyncpg://#postgresql://#; s#^postgresql\+psycopg://#postgresql://#'
}

if [[ "$DB_URL" == sqlite* ]]; then
    SQLITE_PATH="$(echo "$DB_URL" | sed -E 's#^sqlite\+aiosqlite:///##; s#^sqlite:///##; s#\?.*$##')"
    if [[ "$SQLITE_PATH" != /* ]]; then
        SQLITE_PATH="$(pwd)/$SQLITE_PATH"
    fi
    cp "$BACKUP_FILE" "$SQLITE_PATH"
    echo "SQLite restore completed: $SQLITE_PATH"
    exit 0
fi

PG_URL="$(normalize_pg_url "$DB_URL")"
if [[ "$BACKUP_FILE" == *.sql.gz ]]; then
    gunzip -c "$BACKUP_FILE" | psql "$PG_URL"
    echo "PostgreSQL restore completed from compressed SQL backup."
    exit 0
fi

if [[ "$BACKUP_FILE" == *.sql ]]; then
    psql "$PG_URL" -f "$BACKUP_FILE"
    echo "PostgreSQL restore completed from SQL backup."
    exit 0
fi

echo "ERROR: unsupported backup format. Use .sql, .sql.gz, or SQLite .db backup files."
exit 1
