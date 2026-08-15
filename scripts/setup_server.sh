#!/usr/bin/env bash
# 首次在阿里云服务器上执行：安装依赖、克隆仓库、注册 systemd 服务并启动
# 用法：sudo bash scripts/setup_server.sh [仓库地址]
set -euo pipefail

REPO_URL="${1:-https://github.com/ccfarm/invest_tool.git}"
APP_DIR=/opt/invest_tool

echo "==> 安装基础依赖..."
apt update
apt install -y git python3 python3-venv curl

# Ubuntu 自带 nodejs 版本过旧，用 NodeSource 安装 Node 22（Vite 8 需要）
if ! command -v node >/dev/null 2>&1 || [ "$(node -v | tr -d 'v' | cut -d. -f1)" -lt 20 ]; then
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  apt install -y nodejs
fi

echo "==> 克隆仓库..."
if [ ! -d "$APP_DIR/.git" ]; then
  git clone "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"

echo "==> 注册 systemd 服务..."
cp scripts/invest-tool.service /etc/systemd/system/invest-tool.service
systemctl daemon-reload

echo "==> 首次构建并启动..."
bash scripts/deploy_server.sh
systemctl enable invest-tool

IP=$(hostname -I | awk '{print $1}')
echo "==> 完成：http://${IP}:80（记得在阿里云安全组放行 80 端口）"
