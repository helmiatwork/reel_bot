#!/bin/bash
# Creates multiple PostgreSQL databases on first boot
set -e
function create_db() {
    local db=$1
    echo "Creating database: $db"
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
        CREATE DATABASE $db;
        GRANT ALL PRIVILEGES ON DATABASE $db TO $POSTGRES_USER;
EOSQL
}
if [ -n "$POSTGRES_MULTIPLE_DATABASES" ]; then
    for db in $(echo $POSTGRES_MULTIPLE_DATABASES | tr ',' ' '); do
        create_db $db
    done
    echo "All databases created"
fi

echo "Creating workflow_logs table in n8n database"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "n8n" <<-EOSQL
    CREATE TABLE IF NOT EXISTS workflow_logs (
        id            SERIAL PRIMARY KEY,
        execution_id  TEXT UNIQUE,
        workflow_id   TEXT,
        workflow_name TEXT,
        source_url    TEXT,
        started_at    TIMESTAMPTZ DEFAULT NOW(),
        finished_at   TIMESTAMPTZ,
        status        TEXT DEFAULT 'running',
        output_url    TEXT
    );
EOSQL
echo "workflow_logs table ready"
