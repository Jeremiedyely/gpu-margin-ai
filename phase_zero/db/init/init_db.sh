#!/bin/bash
# init_db.sh — Creates the gpu_margin database if it doesn't exist.
# Runs as a one-shot init container after SQL Server is healthy,
# before Flyway migrations.

set -e

echo "Waiting for SQL Server to accept connections..."
for i in $(seq 1 30); do
    /opt/mssql-tools18/bin/sqlcmd \
        -S db -U sa -P "$DB_SA_PASSWORD" \
        -Q "SELECT 1" -C -b -o /dev/null 2>/dev/null \
        && break
    echo "  Attempt $i — not ready yet..."
    sleep 2
done

echo "Running create_database.sql..."
/opt/mssql-tools18/bin/sqlcmd \
    -S db -U sa -P "$DB_SA_PASSWORD" \
    -C -b \
    -i /init/create_database.sql

echo "Database init complete."
