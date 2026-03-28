import sys
from typing import List
from pathlib import Path

from maa.resource import Resource
from maa.tasker import Tasker, LoggingLevelEnum

def find_resource_bundles(root_dirs: List[Path]) -> List[Path]:
    """
    扫描给定目录，智能找出所有符合 MAA 资源包特征的文件夹
    """
    valid_bundles = set() # 使用 set 去重，防止同一个目录被添加多次
    
    for root in root_dirs:
        if not root.exists():
            print(f"⚠️ 警告: 目录不存在 -> {root}")
            continue

        print(f"🔍 正在扫描目录: {root}")

        # 规则 1: 查找包含 'pipeline' 文件夹的目录
        # rglob 会递归查找所有层级。如果找到了 pipeline 文件夹，它的父目录就是我们要的资源包根目录。
        for p in root.rglob("pipeline"):
            if p.is_dir():
                valid_bundles.add(p.parent.resolve())

        # 规则 2: 查找包含 '*pipeline.json' 文件的目录 (支持 pipeline.json, default_pipeline.json 等)
        for p in root.rglob("*pipeline*.json"):
            if p.is_file():
                valid_bundles.add(p.parent.resolve())

    return list(valid_bundles)


def check(dirs: List[Path]) -> bool:
    resource = Resource()
    print(f"🚀 开始检查，共发现 {len(dirs)} 个有效的 MAA 资源包...")

    for dir_path in dirs:
        print(f"  -> 正在加载资源包: {dir_path}")
        # 将 Path 对象转为字符串后传给底层
        status = resource.post_bundle(str(dir_path)).wait().status
        if not status.succeeded:
            print(f"❌ 资源包加载失败: {dir_path}")
            return False
        print(f"✅ 资源包加载成功: {dir_path}")

    print("🎉 所有资源包检查完毕，未发现错误。")
    return True


def main():
    if len(sys.argv) < 2:
        print("Usage: python check_resource.py <directory1> [directory2] ...")
        sys.exit(1)

    Tasker.set_stdout_level(LoggingLevelEnum.All)

    # 1. 获取传入的原始目录参数
    input_dirs = [Path(arg) for arg in sys.argv[1:]]
    
    # 2. 智能筛选出真正的资源包根目录
    target_dirs = find_resource_bundles(input_dirs)

    if not target_dirs:
        print("❌ 错误: 未在指定路径下找到任何符合 MAA 规范的资源包结构！")
        print("请检查是否包含了 pipeline 文件夹或 pipeline.json 等配置文件。")
        sys.exit(1)

    # 3. 将筛选后的目录交给 MAA 框架检查
    if not check(target_dirs):
        sys.exit(1)


if __name__ == "__main__":
    main()