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
            # 1. 解析参数 (兼容字符串和字典形式)
            if hasattr(argv, 'custom_action_param'):
                param_str = getattr(argv, 'custom_action_param', '{}')
                params = json.loads(param_str) if isinstance(param_str, str) else param_str
            elif isinstance(argv, dict):
                params = argv
            else:
                params = {}
            
            # 2. 提取账号 ID (如果没有传，默认为 "0")
            account_id = params.get("account_id", "0")
            
            # 3. 调用我们写好的底层切换逻辑
            PersistentStore.switch_account(account_id)
            
            # 4. 静默放行
            return True
            
        except Exception as e:
            utils.mfaalog.error(f"[Py] ❌ 账号切换检查点执行异常: {e}")
            # 即使发生异常也返回 True，让流程降级继续运行
            return True