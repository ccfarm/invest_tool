#!/usr/bin/env bash
# 验收冒烟测试：启动服务，验证健康检查、搜索接口、页面与 SPA 路由
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -d frontend/dist ]; then
  echo "缺少 frontend/dist，请先运行 npm run build" >&2
  exit 1
fi

cd backend
.venv/bin/uvicorn app.main:app --port 80 >/tmp/smoke_test.log 2>&1 &
UVICORN_PID=$!
trap 'kill $UVICORN_PID 2>/dev/null || true' EXIT

for _ in $(seq 1 20); do
  curl -sf http://127.0.0.1:80/health >/dev/null 2>&1 && break
  sleep 0.5
done

echo "==> /health"
curl -sf http://127.0.0.1:80/health | grep -q '"status":"ok"'

echo "==> /api/search?q=600519"
curl -sf 'http://127.0.0.1:80/api/search?q=600519&page_size=1' | grep -q '"total"'

echo "==> GET / 页面"
curl -sf http://127.0.0.1:80/ | grep -q '<title>股东查询'

echo "==> GET /results?q=600519 SPA 回退"
curl -sf 'http://127.0.0.1:80/results?q=600519' | grep -q '<title>股东查询'

echo "==> 冒烟测试全部通过"
