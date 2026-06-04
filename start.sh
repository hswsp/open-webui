#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

RESET=false
for arg in "$@"; do
    if [ "$arg" = "--reset" ]; then
        RESET=true
    fi
done

echo "============================================"
echo " Open WebUI + 火山引擎 Seedream 一键部署"
echo "============================================"

# --- 1. 检查 .env ---
if [ ! -f .env ]; then
    echo ""
    echo "[1] 创建 .env 文件..."
    cp .env.example .env
    echo "  已从 .env.example 创建 .env"
    echo "  请编辑 .env 填入以下配置："
    echo "    - WEBUI_SECRET_KEY: 任意随机字符串"
    echo "    - OWUI_ADMIN_EMAIL: 管理员邮箱"
    echo "    - OWUI_ADMIN_PASSWORD: 管理员密码"
    echo "    - OWUI_ARK_API_KEY: 火山方舟 API Key（以 ark- 开头）"
    echo ""
    echo "  编辑完成后重新运行: bash start.sh"
    exit 1
fi

# --- 2. 加载 .env ---
echo ""
echo "[2] 加载环境变量..."
set -a; source .env; set +a

required_vars=("WEBUI_SECRET_KEY" "OWUI_ADMIN_EMAIL" "OWUI_ADMIN_PASSWORD" "OWUI_ARK_API_KEY")
missing_vars=()
for var in "${required_vars[@]}"; do
    if [ -z "${!var:-}" ]; then
        missing_vars+=("$var")
    fi
done
if [ ${#missing_vars[@]} -gt 0 ]; then
    echo "  [ERROR] .env 中缺少以下变量:"
    for var in "${missing_vars[@]}"; do echo "    - $var"; done
    echo "  请编辑 .env 后重试"
    exit 1
fi
echo "  环境变量检查通过"

# --- 3. 准备数据目录 ---
echo ""
echo "[3] 准备数据目录..."
OWUI_DATA_DIR="${OWUI_DATA_DIR:-~/open-webui/data}"
OWUI_DATA_DIR="${OWUI_DATA_DIR/#\~/$HOME}"

if $RESET; then
    echo "  --reset 参数已指定，清空数据目录: $OWUI_DATA_DIR"
    docker compose down 2>/dev/null || true
    docker-compose down 2>/dev/null || true
    rm -rf "$OWUI_DATA_DIR"
fi

mkdir -p "$OWUI_DATA_DIR"
export OWUI_DATA_DIR

if [ -f "$OWUI_DATA_DIR/webui.db" ]; then
    echo "  检测到已有数据，跳过自动配置（使用 --reset 可清空重来）"
    HAS_DATA=true
else
    echo "  全新数据目录: $OWUI_DATA_DIR"
    HAS_DATA=false
fi

# --- 4. 启动 Docker ---
echo ""
echo "[4] 启动 Docker 服务..."
if command -v docker-compose &>/dev/null; then
    docker-compose up -d
else
    docker compose up -d
fi

# --- 5. 自动配置（仅首次需要） ---
echo ""
echo "[5] 配置 Open WebUI..."
echo ""
export OWUI_API_BASE="${OWUI_API_BASE:-http://localhost:8081}"
export OWUI_ADMIN_EMAIL OWUI_ADMIN_PASSWORD OWUI_ARK_API_KEY
python3 scripts/setup.py

# --- 6. 替换中间件（每次启动都执行，容器重启后文件不持久化） ---
echo ""
echo "[6] 替换中间件..."
docker cp scripts/middleware.py open-webui:/app/backend/open_webui/utils/middleware.py

echo ""
echo "============================================"
echo " 部署完成！"
echo " 访问地址: ${OWUI_API_BASE:-http://localhost:8081}"
echo " 管理邮箱: ${OWUI_ADMIN_EMAIL}"
echo "============================================"
