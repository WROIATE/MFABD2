from pathlib import Path
import shutil
import sys
import re
import os

# 解决 Windows CI 环境下打印 Emoji 报错的问题
# 本地编辑器报错,作为次选手段,先注释掉看看yml-env效果.
# if hasattr(sys.stdout, 'reconfigure'):
#     sys.stdout.reconfigure(encoding='utf-8')
#     sys.stderr.reconfigure(encoding='utf-8')

try:
    import jsonc
except ImportError as e:
    print("❌ 缺少依赖: json-with-comments")
    print("请运行以下命令安装:")
    print("  pip install json-with-comments")
    print("或")
    print("  pip install -r requirements.txt")
    sys.exit(1)

from configure import configure_ocr_model

working_dir = Path(__file__).parent
install_path = working_dir / Path("install")
version = len(sys.argv) > 1 and sys.argv[1] or "v0.0.1"
target_os = len(sys.argv) > 2 and sys.argv[2] or "win"
# 确保这里能接收到 CI 传进来的版本号，默认为 0.0.0
maa_ver = len(sys.argv) > 3 and sys.argv[3] or "0.0.0"

# def install_deps():
#     if not (working_dir / "deps" / "bin").exists():
#         print("Please download the MaaFramework to \"deps\" first.")
#         print("请先下载 MaaFramework 到 \"deps\"。")
#         sys.exit(1)
# ... (保留原有注释代码) ...

def convert_line_endings(file_path):
    """将文件的换行符统一转换为 Windows 格式 (CRLF)"""
    try:
        # 读取文件内容
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 统一转换为 CRLF
        content = content.replace('\r\n', '\n')  # 先标准化为 LF
        
        # 写回文件
        with open(file_path, 'w', encoding='utf-8', newline='\r\n') as f:
            f.write(content)
        return True
    except Exception as e:
        print(f"转换换行符失败: {file_path} - {str(e)}")
        return False

def process_markdown_files(directory):
    """递归处理目录中的所有 Markdown 文件"""
    success = True
    if directory.exists():
        print(f"处理 Markdown 文件: {directory}")
        # 遍历目录中的所有文件
        for root, _, files in os.walk(directory):
            for file in files:
                file_path = Path(root) / file
                if file_path.suffix.lower() == '.md':  # 只处理 Markdown 文件
                    if convert_line_endings(file_path):
                        print(f"已转换: {file_path}")
                    else:
                        success = False
    return success

def process_json_files(directory):
    """递归处理目录中的所有 JSON 文件"""
    success = True
    if directory.exists():
        print(f"处理 JSON 文件: {directory}")
        # 遍历目录中的所有文件
        for root, _, files in os.walk(directory):
            for file in files:
                file_path = Path(root) / file
                if file_path.suffix.lower() == '.json':  # 只处理 JSON 文件
                    if convert_line_endings(file_path):
                        print(f"已转换: {file_path}")
                    else:
                        success = False
    return success

def install_resource():
    configure_ocr_model()

    # 复制整个 resource 目录
    shutil.copytree(
        working_dir / "assets" / "resource",
        install_path / "resource",
        dirs_exist_ok=True,
    )
    
    # ================= [MFAA布局文件预配置写入开始] =================
    # 单文件适配: 显式复制 assets/mfa_layout.json 到 install/resource/
    # 这样您就不需要改变文件结构，它会自动归位
    layout_src = working_dir / "assets" / "mfa_layout.json"
    if layout_src.exists():
        print(f"📦 检测到自定义布局，正在注入: {layout_src}")
        shutil.copy2(layout_src, install_path / "resource" / "mfa_layout.json")
    # ================= [预配置写入结束] =================

    # 分别处理 MD 和 JSON 文件换行符
    all_success = True
    
    # 1. 处理公告文件夹的 Markdown 文件
    announcement_dir = install_path / "resource" / "Announcement"
    if not process_markdown_files(announcement_dir):
        all_success = False
    
    # 2. 处理 pipeline 文件夹的 JSON 文件
    pipeline_dir = install_path / "resource" / "pipeline"
    if not process_json_files(pipeline_dir):
        all_success = False
    
    # 3. 处理 Changelog.md 文件
    changelog_path = install_path / "resource" / "Changelog.md"
    if changelog_path.exists():
        print(f"处理更新日志文件: {changelog_path}")
        if not convert_line_endings(changelog_path):
            all_success = False
    else:
        print(f"注意: 未找到更新日志文件 {changelog_path}，跳过处理")
    
    if not all_success:
        print("警告: 部分文件换行符转换失败")

    # 复制并更新 interface.json
    shutil.copy2(
        working_dir / "assets" / "interface.json",
        install_path,
    )

    with open(install_path / "interface.json", "r", encoding="utf-8") as f:
        interface = jsonc.load(f)
    
    # 1. 更新根版本字段（保持 CI 原始格式）
    interface["version"] = version
    
    # 2. 动态更新 title 中的版本号
    if "title" in interface:
        # 匹配 "MFABD2)" 后到 " | 游戏版本" 前的所有内容
        pattern = r"(?<=MFABD2\))(.*?)(?=\s*\|\s*游戏版本：)"
        
        # 使用原始版本号，不修改格式
        display_version = f"{version} "
        
        # 执行替换
        new_title = re.sub(
            pattern, 
            display_version,
            interface["title"]
        )
        interface["title"] = new_title

    with open(install_path / "interface.json", "w", encoding="utf-8") as f:
        jsonc.dump(interface, f, ensure_ascii=False, indent=4)

def install_chores():
    shutil.copy2(working_dir / "README.md", install_path)
    shutil.copy2(working_dir / "LICENSE", install_path)
    shutil.copy2(working_dir / "LICENSE-APACHE", install_path)
    shutil.copy2(working_dir / "LICENSE-MIT", install_path)
    
    # 处理 Mac 引导脚本：注入真实版本号
    if "mac" in target_os or "osx" in target_os:
        # [修改] 修正路径：从 scripts/release 获取，且更名了
        script_src_dir = working_dir / "scripts" / "release"
        
        # 1. 处理 AKeySetup (需注入版本号)
        src_script = script_src_dir / "Mac启动方案2-系统环境联网配置_mac.command"
        dst_script = install_path / "2_备案-系统环境联网配置_mac.command"

        if src_script.exists():
            print(f"📦 [Mac] 处理安装脚本，注入 MaaVersion: {maa_ver}")
            try:
                with open(src_script, 'r', encoding='utf-8') as f:
                    content = f.read()

                # 替换占位符 {{MAA_VERSION}}
                # [修改] 强制替换，不依赖 if 检查失败
                new_content = content.replace("{{MAA_VERSION}}", maa_ver)
                
                with open(dst_script, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                
                # 尝试赋予执行权限
                try: os.chmod(dst_script, 0o755)
                except: pass
                
                print(f"✅ 版本号注入完成: {maa_ver}")

            except Exception as e:
                print(f"❌ 处理 Mac 脚本失败: {e}")
                # 失败兜底：至少拷贝过去
                shutil.copy2(src_script, dst_script)
        else:
            print(f"⚠️ 未找到 Mac 脚本源文件: {src_script}")

        # 2. [修改] 处理修复工具 (Fix Permission) - 路径也改到了 scripts/release
        fix_tool_src = script_src_dir / "Mac启动方案1-内置环境修复赋权_mac.command"
        fix_tool_dst = install_path / "1_Mac用户请先双击运行此环境修复.command"
        
        if fix_tool_src.exists():
            print(f"🚑 注入 Mac 修复工具...")
            shutil.copy2(fix_tool_src, fix_tool_dst)
            try: os.chmod(fix_tool_dst, 0o755)
            except: pass
        else:
            print(f"⚠️ 未找到修复工具: {fix_tool_src}")

def install_agent(target_os):
    print("正在安装 Agent...")
    print(f"Installing agent for {target_os}...")
    # 1. 复制 agent 文件夹
    agent_src = working_dir / "agent"
    agent_dst = install_path / "agent"
    if agent_src.exists():
        shutil.copytree(agent_src, agent_dst, dirs_exist_ok=True)
    else:
        print("警告: 未找到 agent 源码目录，请确认代码结构！")

    # 2. 修改 interface.json 注入 Agent 配置
    interface_json_path = install_path / "interface.json"
    
    try:
        with open(interface_json_path, "r", encoding="utf-8") as f:
            interface = jsonc.load(f)

        # 确保 agent 字段存在
        if "agent" not in interface:
            interface["agent"] = {}

         # ==================== [核心路径配置] ====================
        
        # 1. Windows: 嵌入式 Python
        if any(target_os.startswith(p) for p in ["win", "windows"]):
            interface["agent"]["child_exec"] = r"{PROJECT_DIR}/python/python.exe"
            interface["agent"]["child_args"] = ["-u", "-X", "utf8=1", r"{PROJECT_DIR}/agent/main.py"]
        
        # 2. macOS: 智能判断 (有嵌入用嵌入，没嵌入用系统)
        elif any(target_os.startswith(p) for p in ["macos", "darwin", "osx"]):
            # 检查是否有 python/bin/python3
            embedded_python = install_path / "python" / "bin" / "python3"
            
            if embedded_python.exists():
                print("[macOS] 检测到便携版 Python，已启用独立环境模式。")
                # 注意：MaaFramework 在 Mac 下解析 {PROJECT_DIR} 后路径拼接要准确
                # 这里的路径不需要 .exe
                interface["agent"]["child_exec"] = r"{PROJECT_DIR}/python/bin/python3"
            else:
                print("[macOS] 未检测到便携版 Python，回退到系统 python3。")
                interface["agent"]["child_exec"] = "python3"
            
            # Mac 通常不需要 -X utf8=1
            interface["agent"]["child_args"] = ["-u", r"{PROJECT_DIR}/agent/main.py"]
        
        # 3. Linux/Android
        else:
            interface["agent"]["child_exec"] = "python3"
            interface["agent"]["child_args"] = ["-u", r"{PROJECT_DIR}/agent/main.py"]

        with open(interface_json_path, "w", encoding="utf-8") as f:
            jsonc.dump(interface, f, ensure_ascii=False, indent=4)
        print("✅ Agent 配置更新完成")

    except Exception as e:
        print(f"❌ 更新 interface.json 失败: {e}")

if __name__ == "__main__":
    # install_deps()
    install_resource()
    install_chores()
    install_agent(target_os)
    print(f"Install to {install_path} successfully.")