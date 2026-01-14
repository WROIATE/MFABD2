#!/usr/bin/env python3
"""
公告注入工具 (CI专用)
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
    
    # 4. 精准定位构建产物中的公告文件
    #    根据 install.py 的逻辑，assets 被复制到了 install/assets 下
    target_file = repo_root / "install" / "assets" / "resource" / "Announcement" / "1.公告.md"

    # ---------------------------------------------------------
    # 🛠️ 执行注入逻辑
    # ---------------------------------------------------------
    print(f"🔍 [调试] 脚本位置: {script_dir}")
    print(f"📄 [调试] 草稿路径: {draft_file}")
    print(f"🎯 [调试] 目标路径: {target_file}")

    if not draft_file.exists():
        print(f"ℹ️ [跳过] 草稿文件不存在，无需注入")
        return

    if not target_file.exists():
        print(f"❌ [错误] 目标文件未找到！请检查 install.py 是否正确生成了 assets 目录。")
        # 列出 install 目录结构帮助调试
        install_dir = repo_root / "install"
        if install_dir.exists():
            print(f"📂 install 目录内容: {[p.name for p in install_dir.iterdir()]}")
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

    # 注入
    print(f"📝 正在注入版本 {tag_name} 的公告...")
    insert_block = f"{ANCHOR}\n\n### {tag_name} 通知\n{content}\n\n---\n"
    new_text = original_text.replace(ANCHOR, insert_block)

    # 写入
    target_file.write_text(new_text, encoding='utf-8')
    print("✅ 公告注入成功！")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python inject_announcement.py <tag_name>")
        sys.exit(1)
    
    inject_announcement(sys.argv[1])