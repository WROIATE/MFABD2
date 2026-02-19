#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
echo "=========================================="
echo "   macOS 权限/损坏修复工具 (Gatekeeper Fix)"
echo "=========================================="
echo ""
echo "正在修复目录: $DIR"
echo "可能会要求您输入开机密码以获取权限..."
echo ""

# 核心命令：移除隔离属性
sudo xattr -r -d com.apple.quarantine "$DIR" 2>/dev/null
# 备用命令：移除所有扩展属性
sudo xattr -cr "$DIR"

echo ""
echo "✅ 修复完成！"
echo "请关闭此窗口，然后尝试双击运行程序。"
echo "=========================================="
# 保持窗口不关闭，让用户看到结果
read -p "按回车键退出..."