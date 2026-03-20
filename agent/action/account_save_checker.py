import json
import utils
from utils.persistent_store import PersistentStore

from maa.custom_action import CustomAction
from maa.context import Context
from maa.agent.agent_server import AgentServer

# ==============================================================================
# 🔄 账号切换检查点 (Account Switch Checkpoint)
# ==============================================================================
# 核心功能：在流程中途静默读取 account_id，并切换底层存档路径。
# 配合 pipeline_override 或自定义参数使用，无缝衔接多开需求。
# ==============================================================================

@AgentServer.custom_action("SwitchAccountCheckpoint")
class SwitchAccountCheckpointAction(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        """
        执行账号切换逻辑。
        无论成功与否，始终返回 True，以确保不阻断 Pipeline 主流程。
        """
        try:
            # 1. 解析参数
            if hasattr(argv, 'custom_action_param'):
                param_str = getattr(argv, 'custom_action_param', '{}')
                params = json.loads(param_str) if isinstance(param_str, str) else param_str
            elif isinstance(argv, dict):
                params = argv
            else:
                params = {}
            
            # 2. 【核心修复】只有参数存在时才提取，否则跳过
            if "account_id" in params:
                account_id = params["account_id"]
                # 调用底层切换逻辑，它会作为类变量保存在进程中
                PersistentStore.switch_account(account_id)
            else:
                # 跨任务参数丢失时，走这里。我们不做任何操作，
                # 依靠 PersistentStore 进程中常驻的 _current_account_id 继续运行
                pass
            
            return True
            
        except Exception as e:
            utils.mfaalog.error(f"[Py] ❌ 账号切换检查点执行异常: {e}")
            return True