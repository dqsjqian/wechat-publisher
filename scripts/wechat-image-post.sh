#!/bin/bash
# wechat-image-post.sh
# 发布微信公众号贴图（newspic）到草稿箱
# 用法: ./wechat-image-post.sh <markdown文件>
# 所有元数据（title/cover/tags/author）从 markdown frontmatter 读取

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/wechat-image-post.py"

if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo "错误：找不到 $PYTHON_SCRIPT"
    exit 1
fi

# SSL 证书（如需要）
if [ -n "${SSL_CERT_FILE:-}" ]; then
    export SSL_CERT_FILE
fi

exec python3 "$PYTHON_SCRIPT" "$@"
