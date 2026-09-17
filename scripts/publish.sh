#!/usr/bin/env bash
# wechat-publisher: 发布 Markdown 图文到微信公众号草稿箱（自闭环，无外部 CLI 依赖）
# Usage: ./publish.sh <markdown-file> [theme] [highlight]

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 默认配置
DEFAULT_THEME="lapis"
DEFAULT_HIGHLIGHT="solarized-light"
# 凭证文件路径：优先读 WECHAT_CRED_FILE，默认 ~/.wechat-credentials.env
CRED_FILE="${WECHAT_CRED_FILE:-$HOME/.wechat-credentials.env}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 从凭证文件读取环境变量
load_credentials() {
    if [ -z "$WECHAT_APP_ID" ] || [ -z "$WECHAT_APP_SECRET" ]; then
        if [ -f "$CRED_FILE" ]; then
            echo -e "${YELLOW}从凭证文件读取凭证: ${CRED_FILE}${NC}"
            export WECHAT_APP_ID=$(grep "export WECHAT_APP_ID=" "$CRED_FILE" | head -1 | sed 's/.*export WECHAT_APP_ID=//' | tr -d ' ')
            export WECHAT_APP_SECRET=$(grep "export WECHAT_APP_SECRET=" "$CRED_FILE" | head -1 | sed 's/.*export WECHAT_APP_SECRET=//' | tr -d ' ')
        fi
    fi
}

# 检查环境变量
check_env() {
    load_credentials

    if [ -z "$WECHAT_APP_ID" ] || [ -z "$WECHAT_APP_SECRET" ]; then
        echo -e "${RED}环境变量未设置${NC}"
        echo ""
        echo "在 $CRED_FILE 写入："
        echo "  export WECHAT_APP_ID=your_app_id"
        echo "  export WECHAT_APP_SECRET=your_app_secret"
        echo ""
        echo "或手动 export 同名环境变量，或运行："
        echo "  source ./scripts/setup.sh"
        exit 1
    fi
}

check_file() {
    local file="$1"
    if [ ! -f "$file" ]; then
        echo -e "${RED}文件不存在: $file${NC}"
        exit 1
    fi
}

show_help() {
    echo "Usage: $0 <markdown-file> [theme] [highlight]"
    echo ""
    echo "Examples:"
    echo "  $0 article.md"
    echo "  $0 article.md lapis"
    echo "  $0 article.md lapis solarized-light"
    echo ""
    echo "Themes (scripts/themes/*.css):"
    echo "  default, juejin_default, lapis, maize, medium_default,"
    echo "  orangeheart, phycat, pie, purple, rainbow, toutiao_default, zhihu_default"
    echo ""
    echo "Highlights (scripts/themes/highlight/*.css):"
    echo "  atom-one-dark, atom-one-light, dracula, github-dark, github,"
    echo "  monokai, solarized-dark, solarized-light, xcode"
    echo ""
    echo "Extra options (pass through to publish_article.py after --):"
    echo "  $0 article.md lapis github -- --render-only preview.html"
    echo "  $0 article.md -- --no-footnote --no-mac-style"
}

main() {
    if [ $# -eq 0 ] || [ "$1" == "-h" ] || [ "$1" == "--help" ]; then
        show_help
        exit 0
    fi

    local file="$1"
    local theme="${2:-$DEFAULT_THEME}"
    local highlight="${3:-$DEFAULT_HIGHLIGHT}"
    shift $(( $# > 3 ? 3 : $# ))

    check_env
    check_file "$file"

    echo -e "${GREEN}发布图文文章...${NC}"
    echo "  文件: $file"
    echo "  主题: $theme"
    echo "  代码高亮: $highlight"
    echo ""

    python3 "$SCRIPT_DIR/publish_article.py" "$file" \
        --theme "$theme" --highlight "$highlight" "$@"
}

main "$@"
