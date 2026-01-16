# -*- coding: utf-8 -*-

import os
import sys
import platform
from pathlib import Path

# --- 核心修复：添加依赖库路径 ---
current_file_path = Path(__file__).resolve()
project_root = current_file_path.parent.parent  # 指向 install/ 目录
deps_path = project_root / "agent"

# 将 agent 目录加入 python 搜索路径 (解决 fishing_agent 找不到的问题)
if deps_path.exists():
    sys.path.insert(0, str(deps_path))

# -----------------------------
# 1. 动态计算 RID (Runtime Identifier)
system_name = platform.system().lower()  # 'windows', 'linux', 'darwin'
proc_arch = platform.machine().lower()   # 'amd64', 'x86_64', 'aarch64', 'arm64'

# [修复2] 必须给 rid 一个默认值，或者补全 Windows 分支
rid = "win-x64" # 默认值，防崩溃

if system_name == 'windows':
    if 'arm64' in proc_arch:
        rid = "win-arm64"
    else:
        rid = "win-x64"
elif system_name == 'linux':
    rid = "linux-arm64" if 'aarch64' in proc_arch else "linux-x64"
elif system_name == 'darwin':
    rid = "osx-arm64" if 'arm64' in proc_arch else "osx-x64"

# 2. 拼接 Native 库路径
dll_path = project_root / "runtimes" / rid / "native"

# 3. 【关键】在导入 maa 之前，注入环境变量
# 这一步告诉 maa 库去 runtimes 目录找 DLL，而不是去 bin 找
os.environ["MAAFW_BINARY_PATH"] = str(dll_path)

if system_name == 'windows':
    # Windows 额外需要加到 PATH 里
    os.environ["PATH"] = str(dll_path) + os.pathsep + os.environ["PATH"]

from maa.agent.agent_server import AgentServer
from maa.toolkit import Toolkit

# 如果你有自定义动作/识别，在这里导入 (参照 B 项目)
# import my_action 
# import my_reco
import fishing_agent


def main():
    # 设置 stdout 为 utf-8 (防止中文乱码)
    if sys.version_info >= (3, 7):
        sys.stdout.reconfigure(encoding='utf-8')

    print(f"Agent 正在启动... 根目录: {project_root}")

    # 1. 初始化 Toolkit (借鉴 B 项目)
    # 这会读取 interface.json 并自动配置一些环境
    Toolkit.init_option(str(project_root))

    # 2. 获取 socket_id (由 MaaFramework 传入)
    if len(sys.argv) < 2:
        print("错误: 未收到 socket_id 参数，请勿直接运行此脚本，需由 MAA 启动。")
        return
    
    socket_id = sys.argv[-1]
    print(f"Socket ID: {socket_id}")

    # 3. 启动服务
    try:
        AgentServer.start_up(socket_id)
        print("AgentServer 已启动，等待指令...")
        AgentServer.join()
    except Exception as e:
        print(f"Agent 运行发生异常: {e}")
    finally:
        AgentServer.shut_down()
        print("AgentServer 已关闭")

if __name__ == "__main__":
    main()