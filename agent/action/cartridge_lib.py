import json
import time
from datetime import datetime, timedelta
import utils
from maa.custom_action import CustomAction
from maa.context import Context
from maa.agent.agent_server import AgentServer
from utils.persistent_store import PersistentStore # 热更新写入工具

print(f"[Py] 周常管理器已加载 (v2.0 自动存档版)。")

class CooldownManager:
    # ✅ 既然 PersistentStore 是静态类，这里甚至不需要 __init__
    # 但为了保持兼容性，留个空的或者直接删掉都行
    pass

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
            utils.mfaalog.info(f"[Py] 参数解析警告: {e}, argv type: {type(argv)}")
            card_name = "Unknown_Card"

        utils.mfaalog.info(f"----------------------------------------")
        utils.mfaalog.info(f"[Py] 正在检查卡带: {card_name}")

        # ✅ 从防坏档系统里取数据
        # 第二个参数 None 是默认值，如果没记录就返回 None
        last_play_str = PersistentStore.get(card_name, None)

        if last_play_str is None:
            utils.mfaalog.info(f"[Py] 🟢 无历史记录，允许进入。")
            return True
        try:
            last_play_time = datetime.strptime(last_play_str, "%Y-%m-%d %H:%M:%S")
            reset_time = self._get_last_reset_time()
            
            utils.mfaalog.info(f"[Py] 上次吸取: {last_play_str}")
            utils.mfaalog.info(f"[Py] 刷新基准: {reset_time}")

            if last_play_time < reset_time:
                utils.mfaalog.info(f"[Py] 🟢 已过刷新点，允许进入。")
                return True
            else:
                utils.mfaalog.info(f"[Py] 🔴 本周已完成，跳过。")
                return False
        except Exception as e:
            utils.mfaalog.info(f"[Py] ⚠️ 时间解析错误 ({e})，默认允许进入。")
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

        # ✅ 一键保存 (自动完成：写入临时文件 -> 重命名 -> 复制备份)
        PersistentStore.set(card_name, now_str)
        
        utils.mfaalog.info(f"[Py] ✅ {card_name} 记录已更新: {now_str}")
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
            utils.mfaalog.info(f"[Py] CheckCoolDownAction 异常: {e}")
            return False

@AgentServer.custom_action("MarkComplete")
class MarkCompleteAction(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg):
        try:
            return manager.mark_complete(argv)
        except Exception as e:
            utils.mfaalog.info(f"[Py] MarkCompleteAction 异常: {e}")
            return True