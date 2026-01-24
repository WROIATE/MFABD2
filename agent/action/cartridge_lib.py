import json
import os
import time
from datetime import datetime, timedelta, timezone
import utils

# ✅ 引入存档工具
# (不需要改 persistent_store.py，它负责底层读写，这里负责业务逻辑)
from utils.persistent_store import PersistentStore

# --- MFA 核心库 ---
from maa.custom_action import CustomAction
from maa.context import Context
from maa.agent.agent_server import AgentServer

utils.mfaalog.info(f"[Py] 周期策略管理器已加载。")

# ==============================================================================
# 🎮 周期策略管理器 (Cooldown & Cycle Manager)
# ==============================================================================
# 核心功能：基于 [游戏服务器时间] 和 [本地存储] 判断任务是否需要运行。
# 适用场景：日替副本、周常 Boss、半月深渊、限时活动等。
# 特性：支持全球时区设定。开发侧：类设定按照当地时间时区填入，后台自动同步为UTC+0。
#  。                   用户侧：时间戳后台自动同步为UTC+0，不妨碍计算。
# 策略漏洞：忽略了时区变化,时间戳没有时区标记，带电脑旅游历史时间戳的处理未编写应对。
#
# ------------------------------------------------------------------------------
# 📝 JSON Pipeline 配置指南
# ------------------------------------------------------------------------------
# 在 MFA 的 JSON 任务节点中，通过 custom_action_param 传递参数：
#
# "custom_action_param": {
#     "card_name": "Weekly_Boss_Lv5",   // [必填] 任务唯一标识 (ID)
#     "cycle_type": "g_weekly"          // [选填] 策略类型 (对应下方配置的 Key)
#                                       // 若不填，默认使用 第一个有效数组
# }
#
# ------------------------------------------------------------------------------
# ⚙️ 策略配置说明 (CYCLE_STRATEGIES)
# ------------------------------------------------------------------------------
# type             : 周期模式 ("daily" | "weekly" | "semi_monthly" | "interval")
# reset_time       : 刷新时间点 (24小时制字符串，如 "04:00")
# timezone         : 服务器时区 (8=北京时间, 0=UTC, 9=东京时间)
# reset_weekday    : [weekly专用] 刷新日 (0=周一, ... 6=周日)
# reset_days       : [semi_monthly专用] 刷新日期列表 (如 [1, 16])
# anchor_date      : [interval专用] 历史上任意一次刷新日期 ("2024-01-01")
# interval_days    : [interval专用] 间隔天数 (14=双周, 3=每三天)
# blackout_minutes : 结算保护期 (分钟)。在此期间脚本将强制跳过任务。
#
# ==============================================================================
CYCLE_STRATEGIES = {
    # 【实例1】国服/日服手游通用 (当地服务器时间 凌晨4点刷新)
    # "cn_daily": {
    #     "type": "daily",
    #     "reset_time": "04:00",  # 凌晨4点刷新
    #     "timezone": 8,          # UTC+8 北京时间
    #     "blackout_minutes": 0   # 无结算期
    # },
    
    # # 【实例2】国际服通用 (UTC 0点刷新)
    # # 比如: 1999国际服, NIKKE等
    # "global_daily": {
    #     "type": "daily",
    #     "reset_time": "00:00",  # UTC 0点
    #     "timezone": 0,          # UTC+0
    #     "blackout_minutes": 0
    # },

    # # 【实例3】国服周常 (每周一 04:00)
    # "cn_weekly": {
    #     "type": "weekly",
    #     "reset_time": "04:00",
    #     "timezone": 8,
    #     "reset_weekday": 0,     # 周一
    #     "blackout_minutes": 10  # 结算10分钟，防止刚好卡点进不去
    # },

    # # 【实例4】深渊/爬塔 (半月常, 1号/16号刷新)
    # "cn_abyss": {
    #     "type": "semi_monthly",
    #     "reset_time": "04:00",
    #     "timezone": 8,
    #     "reset_days": [1, 16],  # 1号和16号
    #     "blackout_minutes": 60  # 结算1小时 (04:00-05:00不可进入)
    # }

    # # 【实例5】双周/间隔模式 (每14天刷新)
    # "biweekly_event": {
    #     "type": "interval",
    #     "interval_days": 14,          # 14天一循环
    #     "anchor_date": "2024-01-01",  # 锚点：历史上的一天刷新日
    #     "reset_time": "04:00",
    #     "timezone": 8,
    #     "blackout_minutes": 0
    # },
    #
    # #####第一个有效字典数组会被视为默认值!#####
    # 【BD2】国际服-卡带刷新时间周常 (每周一 08:00) 
    "g_weekly": {
        "type": "weekly",
        "reset_time": "08:00",
        "timezone": 8,
        "reset_weekday": 0,     # 周一
        "blackout_minutes": 0   # 无结算期
    },
    # 【BD2】国际服-日常刷新时间 (每天 08:00)
    "g_daily": {
        "type": "daily",
        "reset_time": "08:00",  # UTC 0点
        "timezone": 8,          # UTC+8
        "blackout_minutes": 0
    },
    # 【BD2】国际服-镜中之战刷新时间 (每14天刷新)
    "mirror_pvp": {
        "type": "interval",
        "interval_days": 14,          # 14天一循环
        "anchor_date": "2026-01-25",  # 锚点：历史上的一天刷新日
        "reset_time": "08:00",
        "timezone": 8,
        "blackout_minutes": 180       # 暂时设定,有待确认
    },
    # 【BD2】国际服-黄金竞技场刷新时间 (每14天刷新)
    "golden_pvp": {
        "type": "weekly",
        "reset_time": "24:00",
        "timezone": 8,
        "reset_weekday": 2,     # 周三
        "blackout_minutes": 540  # 结算540分钟，防止刚好卡点进不去
    }
    # # 【BD2】国际服-救赎之塔 (半月常, 1号/16号刷新)时间不确定，暂时不写
    # "g_abyss": {
    #     "type": "semi_monthly",
    #     "reset_time": "04:00",
    #     "timezone": 8,
    #     "reset_days": [1, 16],  # 1号和16号
    #     "blackout_minutes": 60  # 结算1小时 (04:00-05:00不可进入)
    # }
}
# ==============================================================================


class CooldownManager:
    # ✅ 既然 PersistentStore 是静态类，这里甚至不需要 __init__
    def __init__(self):
        pass

    def _get_storage_key(self, card_name, strategy_name):
        """生成唯一存储键名 (防止不同策略共用同一个名字导致冲突)"""
        return f"{card_name}@{strategy_name}"

    def _get_local_timezone(self):
        """获取电脑当前的本地时区"""
        return datetime.now().astimezone().tzinfo

    def _str_to_utc_timestamp(self, time_str):
        """
        【翻译器】: "本地时间字符串" -> "UTC时间戳"
        核心逻辑: 假设存档里的时间是基于当前电脑时区的，将其转为绝对的UTC时间戳。
        """
        try:
            # 1. 解析字符串为 datetime 对象 (naive time)
            dt_naive = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            # 2. 强行给它贴上“当前电脑时区”的标签
            dt_local = dt_naive.replace(tzinfo=self._get_local_timezone())
            # 3. 转换为 UTC 时间戳 (float)
            return dt_local.timestamp()
        except:
            return 0.0

    def _calculate_server_reset_timestamp(self, strategy_name):
        """
        【计算器】: 计算游戏服务器的上一次刷新时间 (UTC戳)
        无论你在地球哪里，这个函数算出的 绝对时间点 都是一致的。
        """
        # 1. 尝试获取指定策略
        config = CYCLE_STRATEGIES.get(strategy_name)

        # 2. 如果没找到（或者 key 写错了），尝试用第一个可用的策略兜底
        if not config:
            # 获取字典里的第一个 key 作为兜底，防止 crash
            fallback_key = next(iter(CYCLE_STRATEGIES))
            config = CYCLE_STRATEGIES[fallback_key]
            utils.mfaalog.warning(f"[Py] ⚠️ 策略 '{strategy_name}' 未定义，已降级使用 '{fallback_key}'")
        
        # 3. 构造游戏服务器的“现在时间”
        server_tz_offset = config.get("timezone", 8)
        server_tz = timezone(timedelta(hours=server_tz_offset))
        now_server = datetime.now(server_tz)

        # 4. 解析基准刷新点 (例如 04:00)
        h, m = map(int, config.get("reset_time", "04:00").split(':'))
        
        cycle_type = config.get("type", "daily")

        # --- 间隔模式 (Interval) 逻辑 v6.0 新增 ---
        if cycle_type == "interval":
            anchor_str = config.get("anchor_date", "2024-01-01")
            interval = config.get("interval_days", 14)
            
            # 构造锚点时间 (带时区)
            anchor_naive = datetime.strptime(anchor_str, "%Y-%m-%d")
            anchor_dt = anchor_naive.replace(hour=h, minute=m, tzinfo=server_tz)
            
            # 算出 锚点 到 现在 过去了多少天
            delta = now_server - anchor_dt
            
            # 向下取整算出经过了多少个周期
            cycles_passed = int(delta.total_seconds() // (interval * 86400))
            
            # 算出最近的一次刷新时间
            final_reset = anchor_dt + timedelta(days=cycles_passed * interval)
            
            return final_reset.timestamp(), config

        # --- 以下是常规逻辑 ---
        
        # 构造今天的刷新点
        base_reset = now_server.replace(hour=h, minute=m, second=0, microsecond=0)
        
        # 如果还没到今天的刷新点，说明上一次刷新是在昨天
        if now_server < base_reset:
            base_reset -= timedelta(days=1)

        # 根据周期类型回溯 (找最近的一个刷新日)
        if cycle_type == "weekly":
            target_wd = config.get("reset_weekday", 0)
            current_wd = base_reset.weekday()
            days_diff = (current_wd - target_wd) % 7
            final_reset = base_reset - timedelta(days=days_diff)

        elif cycle_type == "semi_monthly":
            target_days = config.get("reset_days", [1, 16])
            target_days.sort(reverse=True) # 从大到小排
            
            # 简单粗暴回溯法：从今天往前推，直到撞上刷新日
            check_date = base_reset
            found = False
            for _ in range(32): # 最多往前找一个月
                if check_date.day in target_days:
                    # 还需要确保这个刷新点确实在 now 之前
                    final_reset = check_date
                    found = True
                    break
                check_date -= timedelta(days=1)
            
            if not found: final_reset = base_reset # 兜底

        else: # daily
            final_reset = base_reset

        return final_reset.timestamp(), config

    def check_availability(self, argv):
        # --- 1. 参数解析 (增强健壮性) ---
        try:
            if hasattr(argv, 'custom_action_param'):
                param_str = getattr(argv, 'custom_action_param', '{}')
                params = json.loads(param_str) if isinstance(param_str, str) else param_str
            elif isinstance(argv, dict):
                params = argv
            else:
                params = {}
            
            card_name = params.get("card_name", "Unknown_Card")
            strategy_name = params.get("cycle_type", "g_weekly") # 默认策略
        except Exception as e:
            utils.mfaalog.error(f"[Py] 参数解析失败: {e}")
            return True # 出错放行，避免卡死

        utils.mfaalog.info(f"----------------------------------------")
        utils.mfaalog.info(f"[Py] 检查: {card_name} (策略: {strategy_name})")

        # --- 2. 读取数据库 ---
        # 读出来的是给人看的字符串: "2026-01-24 12:00:00"
        storage_key = self._get_storage_key(card_name, strategy_name)
        last_run_str = PersistentStore.get(storage_key, None)

        # --- 3. 计算服务器刷新时间 (UTC戳) ---
        try:
            reset_ts, config = self._calculate_server_reset_timestamp(strategy_name)
        except Exception as e:
            utils.mfaalog.error(f"[Py] 策略计算异常: {e}")
            return True

        # --- 4. 结算期逻辑 ---
        blackout_min = config.get("blackout_minutes", 0)
        current_ts = time.time() # 绝对的 UTC 时间戳
        settlement_end_ts = reset_ts + (blackout_min * 60)
        
        # 打印给人看 (转为本地时间显示)
        local_reset_str = datetime.fromtimestamp(reset_ts).strftime("%Y-%m-%d %H:%M:%S")
        utils.mfaalog.info(f"[Py] 刷新基准(本地): {local_reset_str}")
        
        # 结算期拦截
        if reset_ts <= current_ts < settlement_end_ts:
            end_str = datetime.fromtimestamp(settlement_end_ts).strftime("%H:%M:%S")
            utils.mfaalog.warning(f"[Py] ⛔ 处于结算期 (结束于 {end_str})")
            return False

        # --- 5. 核心比对 ---
        if last_run_str is None:
            utils.mfaalog.info(f"[Py] 🟢 无历史记录，允许进入。")
            return True

        # 【翻译】: 字符串 -> UTC戳
        last_run_ts = self._str_to_utc_timestamp(last_run_str)
        
        utils.mfaalog.info(f"[Py] 上次运行(本地): {last_run_str}")

        if last_run_ts < reset_ts:
            utils.mfaalog.info(f"[Py] 🟢 记录早于刷新点，允许进入。")
            return True
        else:
            utils.mfaalog.info(f"[Py] 🔴 本周期已完成，跳过。")
            return False

    def mark_complete(self, argv):
        # --- 参数解析 ---
        try:
            if hasattr(argv, 'custom_action_param'):
                param_str = getattr(argv, 'custom_action_param', '{}')
                params = json.loads(param_str) if isinstance(param_str, str) else param_str
            elif isinstance(argv, dict):
                params = argv
            else:
                params = {}
            card_name = params.get("card_name", "Unknown_Card")
            strategy_name = params.get("cycle_type", "g_weekly")
        except:
            card_name = "Unknown_Card"
            strategy_name = "g_weekly"

        # --- 保存逻辑 ---
        storage_key = self._get_storage_key(card_name, strategy_name)
        
        # ✅ 【写入】: 存当前电脑的本地时间字符串
        # 优点: 用户打开 json 看到的是自己墙上挂钟的时间，非常直观
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 自动调用防坏档系统写入
        PersistentStore.set(storage_key, now_str)
        
        utils.mfaalog.info(f"[Py] ✅ 记录已更新: {storage_key} -> {now_str}")
        return True

manager = CooldownManager()

# Action 注册 (无需修改)
@AgentServer.custom_action("CheckCoolDown")
class CheckCoolDownAction(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg):
        return manager.check_availability(argv)

@AgentServer.custom_action("MarkComplete")
class MarkCompleteAction(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg):
        return manager.mark_complete(argv)