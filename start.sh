#!/usr/bin/env bash
# start.sh — 一键启动脚本
# 自动完成：虚拟环境创建 → Python 依赖安装 → Node 依赖安装 → 启动 Web 管理后台
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
WEB_DIR="$SCRIPT_DIR/web"
XHS_SKILLS_DIR="$SCRIPT_DIR/vendor/xiaohongshu-skills"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

step() { echo -e "\n${GREEN}▶ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠  $1${NC}"; }
fail() { echo -e "${RED}✗ $1${NC}"; exit 1; }

# ── 1. 检查 Python 版本 ──────────────────────────────────────────────────────
step "检查 Python 版本"
PYTHON_BIN=""
for candidate in python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" &>/dev/null; then
        ver=$("$candidate" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 11 ]; then
            PYTHON_BIN="$candidate"
            echo "  使用 $candidate ($ver)"
            break
        fi
    fi
done
[ -z "$PYTHON_BIN" ] && fail "需要 Python 3.11+，请先安装: brew install python@3.12"

# ── 2. 创建虚拟环境（如果不存在）────────────────────────────────────────────
step "检查 Python 虚拟环境"
if [ ! -f "$VENV_DIR/bin/python3" ]; then
    echo "  创建虚拟环境 .venv ..."
    "$PYTHON_BIN" -m venv "$VENV_DIR"
    echo "  虚拟环境创建成功"
else
    echo "  虚拟环境已存在，跳过创建"
fi
PIP="$VENV_DIR/bin/pip"
PYTHON="$VENV_DIR/bin/python3"

# ── 3. 安装/更新主项目依赖 ───────────────────────────────────────────────────
step "安装主项目 Python 依赖 (pyproject.toml)"
# 只在 pyproject.toml 比 venv marker 新时重新安装
MARKER="$VENV_DIR/.installed_marker"
if [ ! -f "$MARKER" ] || [ "$SCRIPT_DIR/pyproject.toml" -nt "$MARKER" ]; then
    "$PIP" install --quiet --upgrade pip
    "$PIP" install --quiet -e "$SCRIPT_DIR"
    touch "$MARKER"
    echo "  主项目依赖安装完成"
else
    echo "  主项目依赖无变化，跳过"
fi

# ── 4. 安装 xiaohongshu-skills 依赖 ─────────────────────────────────────────
step "安装 xiaohongshu-skills 依赖 (requests, websockets)"
XHS_MARKER="$VENV_DIR/.xhs_installed_marker"
if [ ! -f "$XHS_MARKER" ] || [ "$XHS_SKILLS_DIR/pyproject.toml" -nt "$XHS_MARKER" ]; then
    if [ -d "$XHS_SKILLS_DIR" ]; then
        "$PIP" install --quiet requests websockets
        touch "$XHS_MARKER"
        echo "  xiaohongshu-skills 依赖安装完成"
    else
        warn "vendor/xiaohongshu-skills 目录不存在，跳过 (git submodule update --init?)"
    fi
else
    echo "  xiaohongshu-skills 依赖无变化，跳过"
fi

# ── 5. 检查 .env 文件 ────────────────────────────────────────────────────────
step "检查 .env 配置"
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    if [ -f "$SCRIPT_DIR/.env.example" ]; then
        cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
        warn ".env 不存在，已从 .env.example 复制 — 请填写 API Key 后重新运行"
        exit 0
    else
        warn ".env 文件不存在，某些功能（Tavily/Gemini/Claude）可能无法运行"
    fi
else
    echo "  .env 文件存在 ✓"
fi

# ── 6. 安装 Node.js 依赖 ─────────────────────────────────────────────────────
step "检查 Node.js 依赖"
if ! command -v node &>/dev/null; then
    fail "未找到 node，请先安装: brew install node"
fi
if ! command -v npm &>/dev/null; then
    fail "未找到 npm，请先安装: brew install node"
fi
echo "  Node $(node --version), npm $(npm --version)"

NODE_MARKER="$WEB_DIR/node_modules/.install_marker"
if [ ! -f "$NODE_MARKER" ] || [ "$WEB_DIR/package.json" -nt "$NODE_MARKER" ]; then
    echo "  安装 Node 依赖 (npm install)..."
    npm install --prefix "$WEB_DIR" --silent
    touch "$NODE_MARKER"
    echo "  Node 依赖安装完成"
else
    echo "  Node 依赖无变化，跳过"
fi

# ── 7. 打印环境信息 ──────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  环境就绪！启动 Web 管理后台...${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo "  Python: $PYTHON"
echo "  Web:    http://localhost:3000"
echo ""
echo -e "  ${YELLOW}提示: Chrome 需要提前以 CDP 调试模式启动才能发布${NC}"
echo -e "  ${YELLOW}      运行 bash scripts/launch_chrome.sh 启动 Chrome${NC}"
echo ""

# ── 8. 启动 Next.js 开发服务器 ──────────────────────────────────────────────
exec npm run dev --prefix "$WEB_DIR"
