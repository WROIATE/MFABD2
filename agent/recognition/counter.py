from maa.custom_recognition import CustomRecognition
from maa.custom_action import CustomAction
from maa.agent.agent_server import AgentServer
import json

# 引入我们封装好的日志工具
from utils import mfaalog as logger

# 🔢 计数与逻辑控制器 (Counter & Logic Controller)
# ==============================================================================
# 核心功能：基于 [内存变量](全局有效) 实现任务次数限制、逻辑分支控制。
# 适用场景：限制副本刷取次数（如每日3次）、防止任务死循环、单次运行中的一次性锁。
# 特性：
#   1. 内存级存储：速度极快，无需读写文件。
#   2. 灵活控制：支持 检查(Check)、更新(Update)、重置(Reset) 三种操作。
#   3. 动态参数：完全通过 pipeline.json 传递参数，无需修改 Python 代码。
#
# 策略缺陷：
#   1. 数据易失：MAA 重启后计数器会清零（保存在 RAM 中）。
#   2. 无法跨进程：如果开启多个 MAA 实例，它们之间的计数不互通。
#
# ------------------------------------------------------------------------------
# 📝 JSON Pipeline 配置指南 (标准规范版)
# ------------------------------------------------------------------------------
#
# 【功能 A】CheckTag 识别计数现状 (作为 "recognition" 使用)
# ---------------------------------------------------
# 逻辑：当前计数 < max -> 识别成功 (执行 action)
#       当前计数 >= max -> 识别失败 (跳过或转到 on_error)
#
# "Task_Farm_Map": {
#     "recognition": "Custom",             // ⚡️ 固定为 Custom
#     "custom_recognition": "CheckTag",    // ⚡️ 指向 Python 类名
#     "custom_recognition_param": {
#         "tag": "Daily_Map_1",            // 唯一标识符
#         "max": 3                         // 最大允许次数
#     },
#     "action": "Click",                   // 检查通过后执行的动作
#     "next": "Task_Settlement",           // 后续流程
#     "on_error": "Next_Task"              // ⚡️ 次数刷满后跳转至此
# }
#
# 【功能 B】UpdateTag - 计数动作 (作为 "action" 使用)
# ---------------------------------------------------
# 逻辑：执行后，指定 tag 的计数 +value。通常放在战斗结算或任务完成处。
#
# "Task_Settlement": {
    # "action": "Custom",                  // ⚡️ 固定为 Custom
    # "custom_action": "UpdateTag",        // ⚡️ 指向 Python 类名
    # "custom_action_param": {
    #     "tag": "Daily_Map_1",            // 必须与 CheckTag 的 tag 一致
    #     "value": 1                       // 计数 +1 ,支持任意整数,可为负数
    # },
#     "next": "Task_Farm_Map"              // ⚡️ 循环回头部再次检查
# }
#
# 【功能 C】ResetTag - 重置计数 (作为 "action" 使用)
# ---------------------------------------------------
# 逻辑：将指定 tag 列表归零。通常放在 StartUp 任务中。
#
# "Task_Init": {
#     "action": "Custom",
#     "custom_action": "ResetTag",
#     "custom_action_param": {
#         "tags": ["Daily_Map_1", "Boss_V2"]  // 支持列表或单个字符串
#     }
# }
# ==============================================================================

# 全局内存数据库
TAG_STORE = {}

# =========================================================
# 1. 识别：检查标签 (Gatekeeper)
# 参数: { "tag": "MyTag", "max": 3 }
# =========================================================
@AgentServer.custom_recognition("CheckTag")
class CheckTag(CustomRecognition):
    def analyze(self, context, argv):
        try:
            params = json.loads(argv.custom_recognition_param)
            tag = params.get("tag")
            # 默认最大值为 1
            max_val = params.get("max", 1) 
            
            # 获取当前值，默认为 0
            current_val = TAG_STORE.get(tag, 0)
            
            # 构造状态字符串，例如: "Daily_Exp (1/3)"
            status_msg = f"{tag} ({current_val}/{max_val})"

            # 逻辑：当前值 < 最大值 -> 通过
            if current_val < max_val:
                # 【修复】detail 必须是字典
                # 我们把状态信息放进 'msg' 字段，同时也打印到日志
                print(f"🟢 [检查通过] {status_msg}")
                
                return CustomRecognition.AnalyzeResult(
                    box=[0,0,0,0], 
                    detail={"msg": status_msg, "current": current_val, "max": max_val} 
                )
            else:
                # 拦截
                print(f"🔴 [检查拦截] {status_msg} 已达上限")
                return None
        except Exception as e:
            logger.error(f"CheckTag 异常: {e}")
            return None

# =========================================================
# 2. 动作：更新标签 (Updater)
# 参数: { "tag": "MyTag", "value": 1 }
# =========================================================
@AgentServer.custom_action("UpdateTag")
class UpdateTag(CustomAction):
    def run(self, context, argv):
        try:
            params = json.loads(argv.custom_action_param)
            tag = params.get("tag")
            value = params.get("value", 1) 
            
            if tag:
                old_val = TAG_STORE.get(tag, 0)
                new_val = old_val + value
                TAG_STORE[tag] = new_val
                
                # 【回调】打印清晰的变动日志
                print(f"📊 [数值变更] {tag}: {old_val} -> {new_val} (变动: {value:+d})")
                return True
            return False
        except Exception as e:
            logger.error(f"UpdateTag 异常: {e}")
            return False

# =========================================================
# 3. 动作：批量重置 (Reset)
# 参数: { "tags": ["TagA", "TagB"] }
# =========================================================
@AgentServer.custom_action("ResetTag")
class ResetTag(CustomAction):
    def run(self, context, argv):
        try:
            params = json.loads(argv.custom_action_param)
            raw_tags = params.get("tags")
            
            target_list = []
            if isinstance(raw_tags, list):
                target_list = raw_tags
            elif isinstance(raw_tags, str):
                target_list = [raw_tags]
                
            reset_logs = []
            for tag in target_list:
                if tag in TAG_STORE:
                    # 只有值不为0时才重置并记录，避免日志刷屏
                    if TAG_STORE[tag] != 0:
                        TAG_STORE[tag] = 0
                        reset_logs.append(tag)
                    
            if reset_logs:
                logger.debug(f"🧹 [重置完成] 已清零标签: {reset_logs}")
            else:
                logger.debug("🧹 [重置跳过] 目标标签已归零或不存在")
                
            return True
        except Exception as e:
            logger.error(f"ResetTag 异常: {e}")
            return False