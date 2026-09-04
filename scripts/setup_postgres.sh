#!/usr/bin/env bash
# 安装并初始化本机 PostgreSQL；凭据只写入服务器 /etc/invest-tool.env。
set -euo pipefail

if ! command -v psql >/dev/null 2>&1; then
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y postgresql postgresql-client
fi
systemctl enable --now postgresql

ENV_FILE=/etc/invest-tool.env
touch "$ENV_FILE"
chmod 600 "$ENV_FILE"
if grep -q '^DATABASE_URL=' "$ENV_FILE"; then
  exit 0
fi

PG_PASSWORD="$(openssl rand -hex 24)"
if sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='invest_tool'" | grep -q 1; then
  sudo -u postgres psql -v ON_ERROR_STOP=1 -c "ALTER ROLE invest_tool WITH LOGIN PASSWORD '$PG_PASSWORD'" >/dev/null
else
  sudo -u postgres psql -v ON_ERROR_STOP=1 -c "CREATE ROLE invest_tool LOGIN PASSWORD '$PG_PASSWORD'" >/dev/null
fi
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='invest_tool'" | grep -q 1; then
  sudo -u postgres createdb -O invest_tool invest_tool
fi
printf '\nDATABASE_URL=postgresql://invest_tool:%s@127.0.0.1:5432/invest_tool\n' "$PG_PASSWORD" >> "$ENV_FILE"
echo "==> PostgreSQL 已初始化（凭据保存在 $ENV_FILE）"
