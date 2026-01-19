#!/bin/bash
cd "$(dirname "$0")"

# === 配置区域 ===
# 🔴 CI 构建时会自动替换这个占位符，不要手动修改
TARGET_MAA_VERSION="{{MAA_VERSION}}"

# 上游 .NET 安装脚本的文件名
DOTNET_SCRIPT="DependencySetup_依赖库安装_mac.sh"

# === 界面美化 ===
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}=======================================${NC}"
echo -e "${BLUE}    MFABD2 Mac 环境一键配置工具       ${NC}"
echo -e "${BLUE}    目标 MAA 版本: $TARGET_MAA_VERSION       ${NC}"
echo -e "${BLUE}=======================================${NC}"

# =======================================================
# 第一步：调用上游脚本安装 .NET (你要补的部分)
# =======================================================
echo -e "\n${GREEN}>>> [1/2] 检查并安装 .NET 运行时...${NC}"

if [ -f "./$DOTNET_SCRIPT" ]; then
    echo -e "正在调用外部脚本: $DOTNET_SCRIPT"
    # 使用 bash 执行，确保权限正确
    bash "./$DOTNET_SCRIPT"
    
    # 检查上一步的执行结果（可选）
    if [ $? -ne 0 ]; then
        echo -e "${YELLOW}⚠️  警告: .NET 安装脚本返回了错误，可能是用户取消或已安装。继续执行下一步...${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  跳过: 未找到文件 $DOTNET_SCRIPT${NC}"
    echo -e "如果是首次运行，请确认解压完整。"
fi

# =======================================================
# 第二步：安装 Python 依赖
# =======================================================
echo -e "\n${GREEN}>>> [2/2] 配置 Python 环境 (MFABD2 组件)...${NC}"

# 1. 检查 Python3
if ! command -v python3 &> /dev/null; then
    echo -e "\n❌ 错误: 未检测到 python3。"
    echo -e "👉 macOS 通常预装了 python3，或者您可以安装 Xcode Command Line Tools。"
    echo -e "👉 您也可以手动去 python.org 下载安装。"
    read -n 1 -s -r -p "按任意键退出..."
    exit 1
fi

echo "✅ 检测到 Python3，准备安装 MAA 依赖..."

# 2. 定义安装包和源
PACKAGES="maafw==$TARGET_MAA_VERSION numpy"
SOURCES=(
    "PyPI Official (Global)|https://pypi.org/simple"
    "Tuna Mirror (China)|https://pypi.tuna.tsinghua.edu.cn/simple"
    "Aliyun Mirror (China)|https://mirrors.aliyun.com/pypi/simple/"
)

# 3. 循环尝试安装
INSTALL_SUCCESS=false

for source_entry in "${SOURCES[@]}"; do
    name="${source_entry%%|*}"
    url="${source_entry##*|}"
    
    echo -e "\n🌐 正在尝试源: $name ..."
    # -U 代表 upgrade，确保版本对齐
    python3 -m pip install -U $PACKAGES -i "$url"
    
    if [ $? -eq 0 ]; then
        echo -e "\n✅ 依赖安装成功！"
        INSTALL_SUCCESS=true
        break
    else
        echo -e "${YELLOW}⚠️  连接此源失败，自动切换下一个...${NC}"
    fi
done

# =======================================================
# 结束
# =======================================================
echo -e "\n${BLUE}=======================================${NC}"
if [ "$INSTALL_SUCCESS" = true ]; then
    echo -e "${GREEN}🎉🎉🎉 全部配置完成！${NC}"
    echo -e "现在您可以双击启动 MFABD2 主程序了。"
else
    echo -e "${RED}❌ Python 依赖安装失败。${NC}"
    echo -e "请检查网络连接后重试。"
fi
echo -e "${BLUE}=======================================${NC}"

read -n 1 -s -r -p "按任意键退出..."