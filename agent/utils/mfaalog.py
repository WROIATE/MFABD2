import sys
import time
from enum import Enum

# 简单的日志等级
class LogLevel(Enum):
    DEBUG = "[DEBUG]"
    INFO = "[INFO]"
    WARN = "[WARN]"
    ERROR = "[ERROR]"

def _log(level: LogLevel, msg: str):
    """
    格式化打印日志，MFA GUI 会捕获这些输出。
    格式: [时间] [等级] 内容
    """
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    print(f"{timestamp} {level.value} {msg}", flush=True)

def debug(msg):
    _log(LogLevel.DEBUG, msg)

def info(msg):
    _log(LogLevel.INFO, msg)

def warning(msg):
    _log(LogLevel.WARN, msg)

def error(msg):
    _log(LogLevel.ERROR, msg)

# 确保输出流是 UTF-8，防止中文乱码
if sys.version_info >= (3, 7):
    sys.stdout.reconfigure(encoding='utf-8') # type: ignore