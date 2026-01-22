import json
import os
import time
from datetime import datetime, timedelta

# --- 引入 MFA 核心库 ---
from maa.custom_action import CustomAction
from maa.context import Context
from maa.agent.agent_server import AgentServer # <--- 新增导入

# --- 1. 路径自动定位 ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
DB_PATH = os.path.join(PROJECT_ROOT, "cartridge_history.json")

print(f"[Python] 冷却管理器已加载。")
print(f"[Python] 数据库路径: {DB_PATH}")

class CooldownManager:
    def __init__(self):
        self.data = {}
        self.load()

    def load(self):
        if os.path.exists(DB_PATH):
            try:
                with open(DB_PATH, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
            except Exception as e:
                print(f"[Python] 读取记录失败: {e}，将创建新记录。")
                self.data = {}
        else:
            self.data = {}

    def save(self):
        try:
            with open(DB_PATH, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[Python] 保存记录失败: {e}")

    def _get_last_reset_time(self):
        now = datetime.now()
        today_weekday = now.weekday()
        reset_point = now.replace(hour=8, minute=0, second=0, microsecond=0)
        days_diff = today_weekday - 0  # 周一 = 0
        reset_point = reset_point - timedelta(days=days_diff)
        if now < reset_point:
            reset_point = reset_point - timedelta(days=7)
        return reset_point

    def check_availability(self, argv):
        # 这里的 argv 可能是 JSON 字符串，也可能是字典，取决于 pipeline 写法
        # 为了稳健，做个类型检查
        try:
            if hasattr(argv, 'custom_action_param'):
                # 如果传进来的是个对象，取它的属性
                param_str = getattr(argv, 'custom_action_param', '{}')
                if isinstance(param_str, str):
                    params = json.loads(param_str)
                else:
                    params = param_str
                card_name = params.get("card_name", "Unknown_Card")
            elif isinstance(argv, dict):
                card_name = argv.get("card_name", "Unknown_Card")
            else:
                card_name = str(argv)
        except Exception as e:
            print(f"[Python] 参数解析警告: {e}, argv type: {type(argv)}")
            card_name = "Unknown_Card"

        print(f"----------------------------------------")
        print(f"[Python] 正在检查卡带: {card_name}")

        if card_name not in self.data:
            print(f"[Python] 🟢 无历史记录，允许进入。")
            return True

        last_play_str = self.data[card_name]
        try:
            last_play_time = datetime.strptime(last_play_str, "%Y-%m-%d %H:%M:%S")
            reset_time = self._get_last_reset_time()
            
            print(f"[Python] 上次吸取: {last_play_str}")
            print(f"[Python] 刷新基准: {reset_time}")

            if last_play_time < reset_time:
                print(f"[Python] 🟢 已过刷新点，允许进入。")
                return True
            else:
                print(f"[Python] 🔴 本周已完成，跳过。")
                return False
        except Exception as e:
            print(f"[Python] ⚠️ 时间解析错误 ({e})，默认允许进入。")
            return True

    def mark_complete(self, argv):
        # 参数解析逻辑同上
        try:
            if hasattr(argv, 'custom_action_param'):
                param_str = getattr(argv, 'custom_action_param', '{}')
                if isinstance(param_str, str):
                    params = json.loads(param_str)
                else:
                    params = param_str
                card_name = params.get("card_name", "Unknown_Card")
            elif isinstance(argv, dict):
                card_name = argv.get("card_name", "Unknown_Card")
            else:
                card_name = str(argv)
        except:
            card_name = "Unknown_Card"

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.data[card_name] = now_str
        self.save()
        print(f"[Python] ✅ {card_name} 记录已更新: {now_str}")
        return True

manager = CooldownManager()

# ==========================================
# 【重点修复】使用装饰器自动注册
# ==========================================

@AgentServer.custom_action("CheckCoolDown")
class CheckCoolDownAction(CustomAction):
    # 【修复】这里使用 CustomAction.RunArg，或者直接不写类型提示也可以
    def run(self, context: Context, argv: CustomAction.RunArg):
        try:
            return manager.check_availability(argv)
        except Exception as e:
            print(f"[Python] CheckCoolDownAction 异常: {e}")
            return False

@AgentServer.custom_action("MarkComplete")
class MarkCompleteAction(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg):
        try:
            return manager.mark_complete(argv)
        except Exception as e:
            print(f"[Python] MarkCompleteAction 异常: {e}")
            return True