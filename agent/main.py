# -*- coding: utf-8 -*-

import os
import sys
from pathlib import Path

# --- 核心修复：添加依赖库路径 ---
# 假设目录结构:
# install/
#   ├── agent/
#   │    └── main.py (本文件)
#   └── deps/ (依赖库)
current_file_path = Path(__file__).resolve()
project_root = current_file_path.parent.parent  # 指向 install/ 目录
deps_path = project_root / "agent"

# 将 agent 目录加入 python 搜索路径
if deps_path.exists():
    sys.path.insert(0, str(deps_path))
# -----------------------------

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