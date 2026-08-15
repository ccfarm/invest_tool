#!/usr/bin/env bash
# 一键启动：构建前端并用单个后端进程同时提供 API 与页面
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d frontend/dist ]; then
  echo "==> 构建前端..."
  (cd frontend && npm install && npm run build)
fi

if [ ! -d backend/.venv ]; then
  echo "==> 初始化后端环境..."
  python3 -m venv backend/.venv
fi
if ! backend/.venv/bin/python -c "import fastapi" >/dev/null 2>&1; then
  echo "==> 安装后端依赖..."
  backend/.venv/bin/pip install -r backend/requirements.txt
fi

echo "==> 启动服务：http://localhost:80"
cd backend
exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 80
