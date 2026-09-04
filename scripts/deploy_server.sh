#!/usr/bin/env bash
# 服务器端部署脚本：由 GitHub Actions 在 git pull 之后调用
# 也支持手动在服务器上执行
set -euo pipefail
cd "$(dirname "$0")/.." # 仓库根目录，默认 /opt/invest_tool

NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)"
if [ "$NODE_MAJOR" -lt 22 ]; then
  echo "==> 升级 Node.js 22..."
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  apt-get install -y nodejs
fi

echo "==> 初始化 PostgreSQL..."
bash scripts/setup_postgres.sh
set -a
. /etc/invest-tool.env
set +a

echo "==> 更新 systemd 单元（数据目录固定在仓库外）..."
cp scripts/invest-tool.service /etc/systemd/system/invest-tool.service
cp scripts/invest-tool-crawler.service /etc/systemd/system/invest-tool-crawler.service
systemctl daemon-reload

echo "==> 构建前端..."
cd frontend
npm install
npm run build
cd ..

echo "==> 准备后端环境..."
if [ ! -d backend/.venv ]; then
  python3 -m venv backend/.venv
fi
if ! backend/.venv/bin/python -c "import psycopg" >/dev/null 2>&1; then
  backend/.venv/bin/pip install -r backend/requirements.txt
fi

echo "==> 停止旧服务并迁移 SQLite 数据..."
systemctl stop invest-tool-crawler 2>/dev/null || true
systemctl stop invest-tool 2>/dev/null || true
if [ -s "${DB_PATH:-/var/lib/invest_tool/shareholders.db}" ]; then
  HOLDINGS_COUNT="$(psql "$DATABASE_URL" -tAc 'SELECT COUNT(*) FROM holdings' 2>/dev/null || echo 0)"
  if [ "${HOLDINGS_COUNT//[[:space:]]/}" = "0" ]; then
    (cd backend && .venv/bin/python -m app.migrate_sqlite_to_postgres \
      "${DB_PATH:-/var/lib/invest_tool/shareholders.db}")
  else
    echo "==> PostgreSQL 已有 $HOLDINGS_COUNT 条持股记录，跳过 SQLite 导入"
  fi
fi

echo "==> 重启服务..."
systemctl enable invest-tool invest-tool-crawler
systemctl restart invest-tool invest-tool-crawler

echo "==> 部署完成"
