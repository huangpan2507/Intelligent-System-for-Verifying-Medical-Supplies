#!/bin/sh
set -eu

psql --username "$POSTGRES_USER" --dbname postgres --set ON_ERROR_STOP=1 \
  --set platform_password="$PLATFORM_DB_PASSWORD" \
  --set verification_password="$VERIFICATION_DB_PASSWORD" <<'SQL'
CREATE USER langflow_platform WITH PASSWORD :'platform_password';
CREATE USER verification_app WITH PASSWORD :'verification_password';
CREATE DATABASE langflow OWNER langflow_platform;
CREATE DATABASE verification OWNER verification_app;
REVOKE ALL ON DATABASE langflow FROM PUBLIC;
REVOKE ALL ON DATABASE verification FROM PUBLIC;
SQL
