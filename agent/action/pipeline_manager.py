import json
from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context
import utils
import random

# ==============================================================================
# 🔧 Pipeline 动态管理器 
# ==============================================================================
# 实现了“影子账本”机制，支持自动记录原值、单点还原、批量重置。
#
# ------------------------------------------------------------------------------
# 1. PatchNode (打补丁 + 自动注册备份)
# ------------------------------------------------------------------------------
# "action": {
#     "type": "Custom",
#     "param": {
#         "custom_action": "PatchNode",   
#                       \\另有,PatchAndClick动作,逻辑一样,可额外点击当前节点box坐标
#         "custom_action_param": {
#             "node": "Battle_Node",
#             "patch": { "next": ["Boss_Win"], "timeout": 30000 },
#             "origin": { "next": ["Normal_Win"], "timeout": 10000 }  <-- 选填：原版数据
#         }
#     }
# }
# * 注意：如果你填了 'origin'，系统会自动把它存入内存。
# * 以后调用 RestoreNode 或 ResetAll 时，不需要再填数据，系统会自动查找。
#
# ------------------------------------------------------------------------------
# 2. RestoreNode (单点还原)
# ------------------------------------------------------------------------------
# "action": {
#     "type": "Custom",
#     "param": {
#         "custom_action": "RestoreNode",
#         "custom_action_param": {
#             "node": "Battle_Node"  <-- 只要名字，系统去账本里找原版数据
#         }
#     }
# }
#
# ------------------------------------------------------------------------------
# 3. ResetAll (一键重置/批量还原)
# ------------------------------------------------------------------------------
# "action": {
#     "type": "Custom",
#     "param": {
#         "custom_action": "ResetAll"  <-- 不需要参数，把所有改过的节点都恢复
#     }
# }
#
# ------------------------------------------------------------------------------
# 4. RunTask (调用子任务)
# ------------------------------------------------------------------------------
# 作用: 运行另一个任务/节点，支持传入临时参数。注意，流程级别调用，参数修改节点跑完就清除了。
# JSON 示例:
# "action": "Custom",
# "custom_action": "RunTask",
# "custom_action_param": {
#     "entry": "Swipe_Common_Node",           // [必填] 入口节点名
#     "param": {                              // [选填] 临时覆盖参数 (只在这次调用生效)
#         "Swipe_Common_Node": {              // 必须包一层节点名
#             "begin": [100, 200, 0, 0],
#             "duration": 500
#         }
#     }
# }
# ==============================================================================

# --- 全局影子账本 ---
# 格式: { "NodeName": { "original_key": "original_value" } }
NODE_BACKUPS = {}

def parse_json_arg(argv: CustomAction.RunArg) -> dict:
    """通用参数解析器"""
    try:
        if not argv.custom_action_param:
            return {}
        if isinstance(argv.custom_action_param, dict):
            return argv.custom_action_param
        return json.loads(str(argv.custom_action_param).strip())
    except Exception as e:
        utils.mfaalog.warning(f"[Py] 参数解析失败: {e}")
        return {}

@AgentServer.custom_action("PatchNode")
class PatchNode(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        global NODE_BACKUPS
        params = parse_json_arg(argv)
        
        target_node = params.get("node")
        patch_data = params.get("patch")
        origin_data = params.get("origin") # 用户手动提供的原版数据

        if not target_node or not patch_data:
            utils.mfaalog.error("[Py] PatchNode 缺参数 (node/patch)")
            return False

        try:
            # 1. 如果用户提供了原版数据，且账本里还没有记录，就记下来
            # (只记第一次，防止多次Patch把账本污染了)
            if origin_data and target_node not in NODE_BACKUPS:
                NODE_BACKUPS[target_node] = origin_data
                utils.mfaalog.info(f"[Py] 📖 已登记节点备份: {target_node}")

            # 2. 执行魔改
            context.override_pipeline({target_node: patch_data})
            utils.mfaalog.info(f"[Py] 🔧 节点 [{target_node}] 已打补丁")
            return True
        except Exception as e:
            utils.mfaalog.error(f"[Py] PatchNode 失败: {e}")
            return False

@AgentServer.custom_action("RestoreNode")
class RestoreNode(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        global NODE_BACKUPS
        params = parse_json_arg(argv)
        target_node = params.get("node")

        if not target_node:
            return False

        # 1. 优先从账本里找
        backup_data = NODE_BACKUPS.get(target_node)
        
        # 2. 如果账本里没有，看看用户有没有临时传 backup 参数 (兼容旧写法)
        if not backup_data:
            backup_data = params.get("backup")

        if not backup_data:
            utils.mfaalog.warning(f"[Py] ⚠️ 无法还原 [{target_node}]：未在Patch时登记origin，也未传入backup参数")
            return False

        try:
            context.override_pipeline({target_node: backup_data})
            utils.mfaalog.info(f"[Py] 🔙 节点 [{target_node}] 已还原")
            
            # 还原后，从账本里移除？通常建议保留，方便反复修改。
            # 如果想移除，可以 del NODE_BACKUPS[target_node]
            return True
        except Exception as e:
            utils.mfaalog.error(f"[Py] RestoreNode 失败: {e}")
            return False

@AgentServer.custom_action("ResetAll")
class ResetAll(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        global NODE_BACKUPS
        
        if not NODE_BACKUPS:
            utils.mfaalog.info("[Py] 🧹 没有需要重置的节点")
            return True
            
        try:
            utils.mfaalog.info(f"[Py] 🧹 正在批量重置 {len(NODE_BACKUPS)} 个节点...")
            
            # 批量还原
            # override_pipeline 支持一次传多个节点 { "A":{...}, "B":{...} }
            context.override_pipeline(NODE_BACKUPS)
            
            utils.mfaalog.info("[Py] ✅ 所有热更改已清除，节点已复原")
            
            # 清空账本
            NODE_BACKUPS.clear()
            return True
        except Exception as e:
            utils.mfaalog.error(f"[Py] ResetAll 异常: {e}")
            return False

@AgentServer.custom_action("RunTask")
class RunTask(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        params = parse_json_arg(argv)
        entry_node = params.get("entry")
        # 新增：读取 override 参数
        override_data = params.get("param", {}) 
        
        if not entry_node:
            return False

        try:
            if override_data:
                utils.mfaalog.info(f"[Py] 🚀 Call Sub: [{entry_node}] (带参数注入)")
                # 第二个参数就是 运行时覆盖，它只在这次运行中生效，不污染全局
                context.run_task(entry_node, override_data)
            else:
                utils.mfaalog.info(f"[Py] 🚀 Call Sub: [{entry_node}]")
                context.run_task(entry_node)
                
            utils.mfaalog.info(f"[Py] ✅ Return: 子任务结束")
            return True
        except Exception as e:
            utils.mfaalog.error(f"[Py] RunTask 异常: {e}")
            return False
        
@AgentServer.custom_action("PatchAndClick")
class PatchAndClick(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        global NODE_BACKUPS
        
        try:
            # --- 步骤 1: 解析参数 & 执行 Patch 逻辑 ---
            params = parse_json_arg(argv)
            target_node = params.get("node")
            patch_data = params.get("patch")
            origin_data = params.get("origin")
            
            # [新增] 读取用户偏移量，格式应为 [x, y]，例如 [100, 0]
            user_offset = params.get("target_offset") 

            if target_node and patch_data:
                # 1.1 登记备份
                if origin_data and target_node not in NODE_BACKUPS:
                    NODE_BACKUPS[target_node] = origin_data
                    utils.mfaalog.info(f"[Py] 📖 (P&C) 已登记节点备份: {target_node}")

                # 1.2 执行魔改
                context.override_pipeline({target_node: patch_data})
                utils.mfaalog.info(f"[Py] 🔧 (P&C) 节点 [{target_node}] 参数已动态替换")
            else:
                utils.mfaalog.warning("[Py] PatchAndClick 缺少 patch 参数，仅执行点击逻辑")

            # --- 步骤 2: 执行点击逻辑 (Click) ---
            box = argv.box
            
            # 使用 getattr 兼容不同版本的 Rect 属性 (w/width, h/height)
            if box:
                w = getattr(box, 'w', getattr(box, 'width', 0))
                h = getattr(box, 'h', getattr(box, 'height', 0))
                
                if w > 0 and h > 0:
                    # 2.1 计算基础中心点
                    cx = box.x + w / 2
                    cy = box.y + h / 2
                    
                    # 2.2 [核心修改] 应用用户自定义偏移 (target_offset)
                    # 坐标系: X向右为正，Y向下为正
                    if user_offset and isinstance(user_offset, list) and len(user_offset) >= 2:
                        off_x = int(user_offset[0])
                        off_y = int(user_offset[1])
                        cx += off_x
                        cy += off_y
                        utils.mfaalog.info(f"[Py] 🎯 应用偏移: [{off_x}, {off_y}]")

                    # 2.3 增加随机微调 (防检测)
                    # 如果你不希望偏移后的点击也被随机化，可以注释掉这两行
                    offset_random = 3
                    cx += random.uniform(-offset_random, offset_random)
                    cy += random.uniform(-offset_random, offset_random)
                    
                    # 2.4 调用底层点击
                    context.tasker.controller.post_click(int(cx), int(cy))
                    utils.mfaalog.info(f"[Py] 🖱️ (P&C) 点击坐标: ({int(cx)}, {int(cy)})")
                    return True
            
            utils.mfaalog.warning("[Py] ⚠️ Patch 成功，但没有有效的识别区域(Box)，无法点击。")
            return True

        except Exception as e:
            utils.mfaalog.error(f"[Py] PatchAndClick 异常: {e}")
            return False