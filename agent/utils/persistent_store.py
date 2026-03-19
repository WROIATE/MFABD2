import json
import os
import shutil
import platform
import re
from pathlib import Path
from . import mfaalog as logger

# ==============================================================================
# 🛠️ 存档系统使用指南 (PersistentStore Usage) - 多账号加强版
# ==============================================================================
# 特性：
# 1. 智能路径: 优先全局系统目录，检测到根目录存档自动切为绿色模式
# 2. 原子写入: 防止断电导致文件损坏 (.tmp 机制)
# 3. 自动备份: 每次写入自动生成 .bak 备份
# 4. 多账号隔离: 通过 switch_account(id) 动态切换读写文件
# ==============================================================================

class PersistentStore:
    APP_NAME = "MFABD2"
    
    # 状态与路径变量
    _initialized = False
    _mode = None
    _current_account_id = "0"  # 默认 0 号存档，接收到的原始 ID
    _sanitized_account_id = "0" # 清洗后的安全 ID，与实际文件名对应
    
    # 动态生成的文件名和路径
    FILE_NAME = "agent_save_data.json"
    BAK_NAME = "agent_save_data.json.bak"
    CONFIG_DIR = None
    FILE_PATH = None
    BACKUP_PATH = None

    @classmethod
    def switch_account(cls, account_id):
        """
        【外部调用接口】切换当前操作的账号存档。
        建议在 Pipeline 的起始“检查点”节点调用此方法。
        """
        # 容错处理：如果是 None 或空，视为 0 号
        if account_id is None or str(account_id).strip() == "":
            safe_id = "0"
        else:
            safe_id = str(account_id).strip()

        # 如果发现传入的账号 ID 与当前不同，触发重置机制
        if safe_id != cls._current_account_id:
            logger.info(f"[Py] 🔄 存档系统检测到账号切换指令: 原账号=[{cls._current_account_id}] -> 新请求=[{safe_id}]")
            cls._current_account_id = safe_id
            cls._initialized = False  # 关键：强制下次重新挂载路径
            cls._init_paths()         # 立即重新初始化并挂载

    @classmethod
    def _init_paths(cls):
        """核心：环境探测与动态路径分配"""
        if cls._initialized:
            return

        # 1. 根据当前 _current_account_id 动态生成文件名和净化 ID
        if cls._current_account_id == "0":
            cls._sanitized_account_id = "0"
            cls.FILE_NAME = "agent_save_data.json"
            cls.BAK_NAME = "agent_save_data.json.bak"
        else:
            # 双重保险：后端过滤系统不支持的路径字符
            original_id = cls._current_account_id
            clean_id = re.sub(r'[\\/*?:"<>|]', "_", original_id)
            cls._sanitized_account_id = clean_id
            cls.FILE_NAME = f"agent_save_data_{clean_id}.json"
            cls.BAK_NAME = f"agent_save_data_{clean_id}.json.bak"
            
            # 记录原始 ID 与实际文件名之间的映射，方便排查问题
            if original_id != clean_id:
                logger.info(f"[Py] ⚠️ 账号 ID 已清洗: 原始='{original_id}', 清洗后='{clean_id}', 映射文件={cls.FILE_NAME}")

        # 获取项目根目录
        base_dir = Path(__file__).resolve().parent.parent.parent
        
        # 2. 检查绿色模式触发条件 (根目录下存在存档或备份文件)
        portable_file = base_dir / cls.FILE_NAME
        portable_bak = base_dir / cls.BAK_NAME
        
        if portable_file.exists() or portable_bak.exists():
            cls._set_portable_mode(base_dir)
        else:
            # 3. 尝试进入全局模式 (并进行权限测试)
            if not cls._try_set_global_mode():
                logger.warning("[Py] ⚠️ 全局目录读写测试失败，自动降级为【绿色便携模式】。")
                cls._set_portable_mode(base_dir)
                
        cls._initialized = True
        
        # 状态汇报 (使用清洗后的 _sanitized_account_id)
        mode_str = "系统全局模式" if cls._mode == 'global' else "绿色便携模式"
        logger.info(f"[Py] 💾 存档挂载完成 | 账号ID: {cls._sanitized_account_id} | 模式: {mode_str}")
        logger.info(f"[Py] 📂 存档路径: {cls.FILE_PATH}")

    @classmethod
    def _set_portable_mode(cls, base_dir: Path):
        """设定为绿色便携模式"""
        cls._mode = 'portable'
        cls.CONFIG_DIR = base_dir
        cls.FILE_PATH = cls.CONFIG_DIR / cls.FILE_NAME
        cls.BACKUP_PATH = cls.CONFIG_DIR / cls.BAK_NAME

    @classmethod
    def _try_set_global_mode(cls) -> bool:
        """尝试设定全局模式，并测试读写权限"""
        system = platform.system()
        if system == "Windows":
            sys_dir = os.getenv("APPDATA") or os.path.expanduser("~")
        elif system == "Darwin":
            sys_dir = os.path.expanduser("~/Library/Application Support")
        else:
            sys_dir = os.getenv("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
            
        config_dir = Path(sys_dir) / cls.APP_NAME
        
        try:
            config_dir.mkdir(parents=True, exist_ok=True)
            test_file = config_dir / ".rw_test.tmp"
            with open(test_file, 'w', encoding='utf-8') as f:
                f.write("test")
            test_file.unlink()
            
            cls._mode = 'global'
            cls.CONFIG_DIR = config_dir
            cls.FILE_PATH = cls.CONFIG_DIR / cls.FILE_NAME
            cls.BACKUP_PATH = cls.CONFIG_DIR / cls.BAK_NAME
            return True
        except Exception as e:
            logger.error(f"[Py] ❌ 系统目录访问异常: {e}")
            return False

    @classmethod
    def load(cls) -> dict:
        """【智能读取】优先读主文件，坏了读备份，完全没有则初始化新档"""
        cls._init_paths()

        assert cls.FILE_PATH is not None
        assert cls.BACKUP_PATH is not None
        
        # 💡纯新账号：主文件和备份都不存在，直接静默初始化
        if not cls.FILE_PATH.exists() and not cls.BACKUP_PATH.exists():
            logger.info(f"[Py] 🌱 账号 [{cls._sanitized_account_id}] 为全新存档，正在初始化...")
            empty_data = {}
            cls._save_file(cls.FILE_PATH, empty_data)
            return empty_data

        if not cls.FILE_PATH.exists() and cls.BACKUP_PATH.exists():
             try:
                 shutil.copy2(cls.BACKUP_PATH, cls.FILE_PATH)
                 logger.info(f"[Py] ✅ 账号 {cls._sanitized_account_id} 已从备份自动生成主存档！")
             except Exception as e:
                 logger.error(f"[Py] ❌ 恢复备份失败: {e}")

        data = cls._try_load_file(cls.FILE_PATH)
        if data is not None:
            return data
            
        logger.warning(f"[Py] ⚠️ 主存档损坏: {cls.FILE_PATH}")
        
        if cls.BACKUP_PATH.exists():
            logger.info(f"[Py] 🔄 正在尝试从备份恢复: {cls.BACKUP_PATH}")
            data = cls._try_load_file(cls.BACKUP_PATH)
            if data is not None:
                logger.info("[Py] ✅ 备份恢复成功！")
                cls._save_file(cls.FILE_PATH, data)
                return data

        logger.error(f"[Py] ❌ 账号 {cls._sanitized_account_id} 存档彻底损坏且无有效备份，重置为空。")
        empty_data = {}
        cls._save_file(cls.FILE_PATH, empty_data)
        return empty_data

    @classmethod
    def _try_load_file(cls, path: Path) -> dict | None:
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                logger.error(f"[Py] ❌ 存档内容不是有效的字典结构: {path}")
                return None
            return data
        except Exception:
            return None

    @classmethod
    def save(cls, data: dict):
        """【安全写入】写主文件 -> 成功 -> 覆盖备份"""
        cls._init_paths()
        assert cls.FILE_PATH is not None
        assert cls.BACKUP_PATH is not None
        
        if cls._save_file(cls.FILE_PATH, data):
            try:
                shutil.copy2(cls.FILE_PATH, cls.BACKUP_PATH)
            except Exception as e:
                logger.warning(f"[Py] 备份更新失败 (不影响主流程): {e}")

    @classmethod
    def _save_file(cls, path: Path, data: dict) -> bool:
        try:
            tmp_path = path.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            shutil.move(tmp_path, path)
            return True
        except Exception as e:
            logger.error(f"[Py] 写入文件失败 {path}: {e}")
            return False

    @classmethod
    def get(cls, key: str, default=None):
        data = cls.load()
        return data.get(key, default)

    @classmethod
    def set(cls, key: str, value):
        data = cls.load()
        data[key] = value
        cls.save(data)