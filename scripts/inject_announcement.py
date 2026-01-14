#!/usr/bin/env python3
"""
公告注入工具 (CI专用 - 基于 install.py )
"""
import os
import sys
from pathlib import Path

def inject_announcement(tag_name):
    # ---------------------------------------------------------
    # 📍 路径定位
    # ---------------------------------------------------------
    # 1. 脚本所在目录 (即 scripts/)
    script_dir = Path(__file__).resolve().parent
    
    # 2. 仓库根目录 (脚本的上一级)
    repo_root = script_dir.parent
    
    # 3. 自动定位草稿文件 (默认就在脚本旁边)
    draft_file = script_dir / "draft_app_msg.md"
    
    # 【修正】根据 install.py 的 shutil.copytree 逻辑：
    # 源: assets/resource -> 目标: install/resource
    # 所以 assets 这一层目录在构建产物中是不存在的
    target_file = repo_root / "install" / "resource" / "Announcement" / "1.公告.md"

    print(f"📍 [定位] 脚本位置: {script_dir}")
    print(f"📄 [调试] 草稿路径: {draft_file}")
    print(f"📍 [定位] 目标路径: {target_file}")

    # --- 2. 检查与读取 ---
    if not draft_file.exists():
        print(f"ℹ️ [跳过] 草稿文件不存在，无需注入")
        return

    # 检查目标文件是否存在 (这次路径应该是 100% 正确的)
    if not target_file.exists():
        print(f"❌ [错误] 目标文件未找到: {target_file}")
        print("请检查 install.py 是否成功执行了资源复制步骤。")
        # 打印一下 install 目录结构，死个明白
        install_dir = repo_root / "install"
        if install_dir.exists():
            print(f"📂 install 根目录内容: {[p.name for p in install_dir.iterdir()]}")
            res_dir = install_dir / "resource"
            if res_dir.exists():
                 print(f"📂 resource 目录内容: {[p.name for p in res_dir.iterdir()]}")
        sys.exit(1)

    # 读取草稿
    content = draft_file.read_text(encoding='utf-8').strip()
    if not content:
        print("ℹ️ [跳过] 草稿内容为空")
        return
    
    # --- 3. 打印即将写入的内容 (Log回调) ---
    print("\n" + "="*30)
    print(f"📢 准备注入版本: {tag_name}")
    print(f"📄 草稿内容预览:\n{content}")
    print("="*30 + "\n")

    original_text = target_file.read_text(encoding='utf-8')
    ANCHOR = "<!-- Msg-Anch -->"

    if ANCHOR not in original_text:
        print(f"⚠️ [警告] 锚点 '{ANCHOR}' 未找到，跳过注入。")
        return

    # --- 3. 执行注入 ---
    insert_block = f"{ANCHOR}\n\n### {tag_name} 通知\n{content}\n\n---\n"
    new_text = original_text.replace(ANCHOR, insert_block)

    target_file.write_text(new_text, encoding='utf-8')
    print(f"✅ [成功] 公告已注入到: {target_file}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python inject_announcement.py <tag_name>")
        sys.exit(1)
    
    inject_announcement(sys.argv[1])