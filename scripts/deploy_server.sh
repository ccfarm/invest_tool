#!/usr/bin/env bash
# 服务器端部署脚本：由 GitHub Actions 在 git pull 之后调用
# 也支持手动在服务器上执行
set -euo pipefail
cd "$(dirname "$0")/.." # 仓库根目录，默认 /opt/invest_tool

echo "==> 构建前端..."
cd frontend
npm ci
npm run build
cd ..

echo "==> 准备后端环境..."
if [ ! -d backend/.venv ]; then
  python3 -m venv backend/.venv
fi
if ! backend/.venv/bin/python -c "import fastapi" >/dev/null 2>&1; then
  backend/.venv/bin/pip install -r backend/requirements.txt
fi

echo "==> 重启服务..."
if systemctl list-unit-files | grep -q '^invest-tool.service'; then
  systemctl restart invest-tool
else
  pkill -f 'uvicorn app.main:app' || true
  (
    cd backend
    nohup .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 \
      >/tmp/invest_tool.log 2>&1 &
  )
fi

echo "==> 部署完成"
