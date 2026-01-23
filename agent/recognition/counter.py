from maa.custom_recognition import CustomRecognition
from maa.custom_action import CustomAction
from maa.agent.agent_server import AgentServer
import json

# 引入我们封装好的日志工具
from utils import mfaalog as logger

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
                logger.info(f"🟢 [检查通过] {status_msg}")
                
                return CustomRecognition.AnalyzeResult(
                    box=[0,0,0,0], 
                    detail={"msg": status_msg, "current": current_val, "max": max_val} 
                )
            else:
                # 拦截
                logger.info(f"🔴 [检查拦截] {status_msg} 已达上限")
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
                logger.info(f"📊 [数值变更] {tag}: {old_val} -> {new_val} (变动: {value:+d})")
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
                logger.info(f"🧹 [重置完成] 已清零标签: {reset_logs}")
            else:
                logger.debug("🧹 [重置跳过] 目标标签已归零或不存在")
                
            return True
        except Exception as e:
            logger.error(f"ResetTag 异常: {e}")
            return False