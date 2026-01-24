import json
import os
import shutil
from pathlib import Path
from . import mfaalog as logger

# ==============================================================================
# 🛠️ 存档系统使用指南 (PersistentStore Usage)
# ==============================================================================
#
# 该模块实现了自动化的数据持久化，具备以下特性：
# 1. 原子写入 (Atomic Write): 防止断电导致文件损坏
# 2. 自动备份 (Auto Backup): 每次写入自动生成 .bak 备份
# 3. 自动恢复 (Auto Restore): 主文件损坏时尝试从备份恢复
#
# ------------------------------------------------------------------------------
# 1. 获取数据 (GET)
# ------------------------------------------------------------------------------
# 方法: PersistentStore.get(key, default_value)
# 
# 参数:
#   - key (str): 数据的唯一键名 (如 "LastRun_Daily")
#   - default_value (Any): 如果没找到记录，返回的默认值 (通常设为 None, 0, 或 False)
#
# 示例:
#   # 获取上次运行时间，如果没记录则返回 None
#   last_play_str = PersistentStore.get(card_name, None)
#
# ------------------------------------------------------------------------------
# 2. 保存数据 (SET)
# ------------------------------------------------------------------------------
# 方法: PersistentStore.set(key, value)
#
# 参数:
#   - key (str): 数据的唯一键名
#   - value (Any): 要保存的数据 (支持字符串、数字、列表、字典)
#
# 示例:
#   # 记录当前时间，系统会自动处理写入硬盘和备份
#   PersistentStore.set(card_name, "2026-01-24 12:00:00")
#
# ==============================================================================

class PersistentStore:
    # 设定存档位置
    BASE_DIR = Path(__file__).parent.parent.parent # 退回3层到根目录
    CONFIG_DIR = BASE_DIR # / "config" # 偏要放根目录!
    FILE_PATH = CONFIG_DIR / "agent_save_data.json"
    # 备份文件路径
    BACKUP_PATH = CONFIG_DIR / "agent_save_data.json.bak"

    @classmethod
    def _ensure_env(cls):
        """确保目录存在"""
        if not cls.CONFIG_DIR.exists():
            cls.CONFIG_DIR.mkdir(parents=True)

    @classmethod
    def load(cls) -> dict:
        """【智能读取】优先读主文件，坏了读备份，再坏了才重置"""
        cls._ensure_env()
        
        # 0：如果主文件不存在，但备份文件存在，先尝试恢复备份 ---
        if not cls.FILE_PATH.exists() and cls.BACKUP_PATH.exists():
             print(f"👀 未找到主存档，但发现备份文件，正在恢复...")
             # 偷个懒，直接把备份重命名为主文件
             try:
                 shutil.copy2(cls.BACKUP_PATH, cls.FILE_PATH)
                 logger.info("✅ 已从备份自动生成主存档！")
             except Exception as e:
                 logger.error(f"恢复备份失败: {e}")

        # 1. 尝试读取主文件
        data = cls._try_load_file(cls.FILE_PATH)
        if data is not None:
            return data
            
        logger.warning(f"⚠️ 主存档损坏: {cls.FILE_PATH}")
        
        # 2. 主文件坏了，尝试读取备份文件
        if cls.BACKUP_PATH.exists():
            logger.info(f"🔄 正在尝试从备份恢复: {cls.BACKUP_PATH}")
            data = cls._try_load_file(cls.BACKUP_PATH)
            if data is not None:
                # 恢复成功！把备份覆盖回主文件
                logger.info("✅ 备份恢复成功！")
                cls._save_file(cls.FILE_PATH, data) # 修复主文件
                return data

        # 3. 实在没救了（备份也不存在或也坏了），只能重置
        logger.error("❌ 存档彻底损坏且无有效备份，重置为空。")
        empty_data = {}
        cls._save_file(cls.FILE_PATH, empty_data)
        return empty_data

    @classmethod
    def _try_load_file(cls, path: Path) -> dict | None:
        """底层读取逻辑，返回 None 表示读取失败"""
        if not path.exists():
            return {} # 文件不存在视为新文件，返回空字典
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None # 读取失败

    @classmethod
    def save(cls, data: dict):
        """【安全写入】写主文件 -> 成功 -> 覆盖备份"""
        cls._ensure_env()
        
        # 1. 先写入主文件
        if cls._save_file(cls.FILE_PATH, data):
            # 2. 主文件写入成功后，更新备份
            # 这样保证了备份文件永远是上一次“完好”的状态
            try:
                shutil.copy2(cls.FILE_PATH, cls.BACKUP_PATH)
            except Exception as e:
                print(f"备份更新失败 (不影响主流程): {e}")

    @classmethod
    def _save_file(cls, path: Path, data: dict) -> bool:
        """底层写入逻辑"""
        try:
            # 使用临时文件写入，防止写一半断电导致文件内容截断
            # 逻辑：写入 .tmp -> 重命名为 .json (重命名是原子操作，极难损坏)
            tmp_path = path.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            # 覆盖原文件
            shutil.move(tmp_path, path)
            return True
        except Exception as e:
            logger.error(f"写入文件失败 {path}: {e}")
            return False

    # --- 便捷接口 ---
    @classmethod
    def get(cls, key: str, default=None):
        data = cls.load()
        return data.get(key, default)

    @classmethod
    def set(cls, key: str, value):
        data = cls.load()
        data[key] = value
        cls.save(data)