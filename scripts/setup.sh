#!/usr/bin/env bash
# setup.sh - 从凭证文件加载微信公众号环境变量
# Usage: source ./scripts/setup.sh

CRED_FILE="${WECHAT_CRED_FILE:-$HOME/.wechat-credentials.env}"

# 检查凭证文件是否存在
if [ ! -f "$CRED_FILE" ]; then
    echo "❌ 找不到凭证文件: $CRED_FILE"
    echo ""
    echo "请创建该文件并写入微信公众号凭证："
    echo ""
    echo "export WECHAT_APP_ID=your_app_id"
    echo "export WECHAT_APP_SECRET=your_app_secret"
    echo ""
    echo "或用 WECHAT_CRED_FILE 环境变量指定其他路径"
    exit 1
fi

# 从凭证文件提取凭证
WECHAT_APP_ID=$(grep "export WECHAT_APP_ID=" "$CRED_FILE" | head -1 | sed 's/.*export WECHAT_APP_ID=//' | tr -d ' ')
WECHAT_APP_SECRET=$(grep "export WECHAT_APP_SECRET=" "$CRED_FILE" | head -1 | sed 's/.*export WECHAT_APP_SECRET=//' | tr -d ' ')

# 检查是否成功提取
if [ -z "$WECHAT_APP_ID" ] || [ -z "$WECHAT_APP_SECRET" ]; then
    echo "❌ 无法从凭证文件读取凭证！"
    echo ""
    echo "请确保 $CRED_FILE 包含以下格式："
    echo ""
    echo "export WECHAT_APP_ID=your_app_id"
    echo "export WECHAT_APP_SECRET=your_app_secret"
    exit 1
fi

# 设置环境变量
export WECHAT_APP_ID
export WECHAT_APP_SECRET

echo "✅ 微信公众号环境变量已加载！"
echo ""
echo "  WECHAT_APP_ID=${WECHAT_APP_ID:0:10}..."
echo "  WECHAT_APP_SECRET=****** (已隐藏)"
echo ""
echo "💡 提示：这些变量仅在当前 shell 会话有效"
