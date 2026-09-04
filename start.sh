#!/usr/bin/env bash
# 一键启动：Next.js 提供页面和 API，Python 仅负责采集任务
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d backend/.venv ]; then
  echo "==> 初始化后端环境..."
  python3 -m venv backend/.venv
fi
if ! backend/.venv/bin/python -c "import fastapi" >/dev/null 2>&1; then
  echo "==> 安装 Python 采集依赖..."
  backend/.venv/bin/pip install -r backend/requirements.txt
fi

echo "==> 安装并构建 Next.js..."
(cd frontend && npm install && npm run build)
echo "==> 启动服务：http://localhost:80"
cd frontend
PYTHON_BIN="$(pwd)/../backend/.venv/bin/python" exec npm start
