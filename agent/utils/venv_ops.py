import os
import sys
import subprocess
import site
from pathlib import Path
from . import mfaalog  # 日志工具

# ---------------------------------------------------------
# 配置区：在这里指定开发环境下强制需要的版本
# 这解决了 requirements.txt 里没有 maafw 的问题
# ---------------------------------------------------------
DEV_MAAFW_VERSION = "5.4.2" 
# 定义虚拟环境文件夹名称
VENV_NAME = ".venv"
# ---------------------------------------------------------

def get_venv_path(project_root: Path) -> Path:
    return project_root / VENV_NAME

def is_running_in_venv() -> bool:
    """检查当前是否已经在虚拟环境中运行"""
    # 核心原理：比较 sys.prefix (当前环境) 和 sys.base_prefix (系统环境)
    return sys.prefix != sys.base_prefix

def get_venv_executable(venv_path: Path) -> Path:
    """获取虚拟环境中的 python.exe 路径"""
    if sys.platform == "win32":
        return venv_path / "Scripts" / "python.exe"
    else:
        return venv_path / "bin" / "python"

def create_venv(venv_path: Path):
    """如果不存在，创建虚拟环境"""
    if venv_path.exists() and (venv_path / "pyvenv.cfg").exists():
        mfaalog.debug("虚拟环境已存在，跳过创建")
        return

    mfaalog.info(f"正在创建虚拟环境: {venv_path} ...")
    try:
        # 使用 venv 模块创建
        subprocess.check_call([sys.executable, "-m", "venv", str(venv_path)])
        mfaalog.info("虚拟环境创建成功")
    except subprocess.CalledProcessError as e:
        mfaalog.error(f"创建虚拟环境失败: {e}")
        raise

def install_deps(venv_python: Path, project_root: Path):
    """
    1. 安装 requirements.txt (通用依赖)
    2. 强制安装 maafw (特定版本)
    """
    # --- 第1步：安装 requirements.txt (这里面没有 maa) ---
    req_file = project_root / "requirements.txt"
    if req_file.exists():
        mfaalog.info("正在同步 requirements.txt (通用依赖)...")
        # 这里的关键是使用 venv 里的 python 去执行 pip
        subprocess.check_call([
            str(venv_python), "-m", "pip", "install", 
            "-i", "https://pypi.tuna.tsinghua.edu.cn/simple", # 国内源
            "-r", str(req_file)
        ])
    
    # --- 第2步：强制补全 maafw (核心修复) ---
    # 模拟 CI 的行为，不管 txt 里有没有，这里强行装上匹配的版本
    mfaalog.info(f"正在强制注入 maafw=={DEV_MAAFW_VERSION} ...")
    try:
        subprocess.check_call([
            str(venv_python), "-m", "pip", "install",
            "-i", "https://pypi.tuna.tsinghua.edu.cn/simple",
            f"maafw=={DEV_MAAFW_VERSION}"
        ])
    except Exception as e:
        mfaalog.warning(f"指定版本安装失败: {e}，尝试模糊匹配...")
        # 如果指定版本失败，尝试安装 5.4 系列的最新版
        subprocess.check_call([
            str(venv_python), "-m", "pip", "install",
            "-i", "https://pypi.tuna.tsinghua.edu.cn/simple",
            "maafw>=5.4,<5.5"
        ])
    
    mfaalog.info("所有依赖安装/检查完成")

def ensure_venv(project_root: Path):
    """
    主逻辑：
    1. 检查是否在 venv 里
    2. 如果不是，检查/创建 venv，安装依赖，然后重启自身
    """
    if is_running_in_venv():
        mfaalog.debug("当前已在虚拟环境中运行")
        return

    venv_path = get_venv_path(project_root)
    venv_python = get_venv_executable(venv_path)

    # 1. 创建环境
    create_venv(venv_path)

    # 2. 安装依赖 (为了加快启动速度，可以加个标记文件判断是否需要更新，这里简化为每次检查)
    install_deps(venv_python, project_root)

    # 3. 重启自身
    mfaalog.info(f"正在切换到虚拟环境: {venv_python}")
    
    # 构建新的启动命令
    # sys.argv[0] 是当前脚本路径，sys.argv[1:] 是参数 (socket_id)
    args = [str(venv_python), sys.argv[0]] + sys.argv[1:]
    
    mfaalog.info(">>> 重启 Agent 进程 >>>")
    
    # 核心魔法：用新的 Python 进程替换当前进程
    if sys.platform == "win32":
        subprocess.run(args)
        sys.exit(0) # 退出当前旧进程
    else:
        os.execv(str(venv_python), args)