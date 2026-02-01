import json
import re
import os
import copy
import random
from pathlib import Path
from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context
import utils

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
# ------------------------------------------------------------------------------
# 1. PatchBatch (批量修改 + 自动注册备份)
# ------------------------------------------------------------------------------
# "action": {
#             "type": "Custom",
#             "param": {
#                 "custom_action": "PatchBatch",
#                 "custom_action_param": {
#                     "patches": {
#                         "Battle_Node": { "next": ["Boss_Win"], "timeout": 30000 },
#                         "Swipe_Common": { "duration": 500 }
#                     },
#                     "origins": {
#                         "Battle_Node": { "next": ["Normal_Win"], "timeout": 10000 },
#                         "Swipe_Common": { "duration": 1000 }
#                     }
#                 }
#             }
# ------------------------------------------------------------------------------
# 2. PatchAndClick (魔改 + 偏移点击)
# ------------------------------------------------------------------------------
# 场景：识别到入口 -> 1.修改后续节点参数 -> 2.点击当前识别位置(支持偏移)
#
# JSON 示例:
# "action": "Custom",
# "custom_action": "PatchAndClick",
# "custom_action_param": {
#     "node": "Battle_Logic",
#     "patch": { "next": ["Boss_Win"] },
#     "origin": { "next": ["Common_Win"] },
#
#     // [选填] 点击偏移量 [x, y, 0, 0]
#     // 说明：X为正向右，Y为正向下。
#     // 建议写满 4 位以符合 MFA 数据规范，程序只取前两位。
#     "target_offset": [100, 50, 0, 0]
# }
# ==============================================================================
# ------------------------------------------------------------------------------
# 3. RestoreNode (单点还原)
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
# 4. ResetAll (一键重置/批量还原)
# ------------------------------------------------------------------------------
# "action": {
#     "type": "Custom",
#     "param": {
#         "custom_action": "ResetAll"  <-- 不需要参数，把所有改过的节点都恢复
#     }
# }
#
# ------------------------------------------------------------------------------
# 5. RunTask (调用子任务)
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
NODE_BACKUPS = {}          # 影子账本：记录被修改节点的原值
ALL_NODES_CACHE = {} 
CACHE_LOADED = False

def parse_json_arg(argv: CustomAction.RunArg) -> dict:
    """通用参数解析器"""
    try:
        if not argv.custom_action_param: return {}
        if isinstance(argv.custom_action_param, dict): return argv.custom_action_param
        return json.loads(str(argv.custom_action_param).strip())
    except: return {}

def _ensure_cache_loaded(force_refresh=False):
    """
    [核心] 扫描所有文件，建立本地节点配置数据库。
    """
    global ALL_NODES_CACHE, CACHE_LOADED
    
    if CACHE_LOADED and not force_refresh:
        return

    utils.mfaalog.info("[Py] 💾 正在建立节点数据库 (Deep Cache)...")
    ALL_NODES_CACHE = {} 

    # 1. 定位目录
    base_dir = Path(".") 
    target_path = base_dir / "resource" / "pipeline"
    if not target_path.exists():
        found = list(base_dir.rglob("pipeline"))
        if found: target_path = found[0]

    if not target_path.exists():
        utils.mfaalog.error(f"[Py] ❌ 找不到 pipeline 目录")
        return

    # 2. 扫描并存储内容
    count = 0
    for file_path in target_path.rglob("*.json"):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content_str = f.read()
                content_str = re.sub(r"//.*", "", content_str) # 简单去注释
                data = json.loads(content_str)
            
            if isinstance(data, dict):
                for node_name, node_config in data.items():
                    ALL_NODES_CACHE[node_name] = node_config
                    count += 1
        except Exception as e:
            utils.mfaalog.warning(f"[Py] 读取跳过 {file_path.name}: {e}")

    CACHE_LOADED = True
    utils.mfaalog.info(f"[Py] 💾 数据库构建完成！已索引 {count} 个节点的原始配置。")

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
            
            # [读取] 偏移量
            user_offset = params.get("target_offset") 

            if target_node and patch_data:
                # 1.1 登记备份
                if origin_data and target_node not in NODE_BACKUPS:
                    NODE_BACKUPS[target_node] = origin_data
                    utils.mfaalog.info(f"[Py] 📖 (P&C) 已登记节点备份: {target_node}")

                # 1.2 执行魔改
                context.override_pipeline({target_node: patch_data})
                print(f"[Py] 🔧 (P&C) 节点 [{target_node}] 参数已动态替换")
            else:
                print("[Py] PatchAndClick 缺少 patch 参数，仅执行点击逻辑")

            # --- 步骤 2: 执行点击逻辑 (Click) ---
            box = argv.box
            
            if box:
                # 兼容属性获取
                w = getattr(box, 'w', getattr(box, 'width', 0))
                h = getattr(box, 'h', getattr(box, 'height', 0))
                
                # 只有当识别到了东西，或者用户想盲点（虽然通常必须有box）
                if w > 0 and h > 0:
                    # 默认点击识别区域的中心
                    final_x = box.x + w / 2
                    final_y = box.y + h / 2
                    
                    # [核心逻辑] 处理自定义偏移
                    if user_offset:
                        # 🔒 严格模式：必须是 4 位数组 [dx, dy, w, h]
                        if not isinstance(user_offset, list) or len(user_offset) != 4:
                            print(f"[Py] ❌ 参数错误: target_offset 必须包含 4 个值 [dx, dy, w, h]。当前: {user_offset}")
                            return False
                        
                        off_dx = int(user_offset[0])
                        off_dy = int(user_offset[1])
                        off_w  = int(user_offset[2])
                        off_h  = int(user_offset[3])
                        
                        # 计算新区域的左上角
                        target_x = box.x + off_dx
                        target_y = box.y + off_dy
                        
                        # 计算新区域的中心点 (如果是 0,0 则就是左上角本身)
                        final_x = target_x + off_w / 2
                        final_y = target_y + off_h / 2
                        
                        utils.mfaalog.info(f"[Py] 🎯 应用精确偏移: 基准({box.x},{box.y}) -> 偏移[{off_dx},{off_dy},{off_w},{off_h}]")

                    # 移除随机微调，相信作者的设定
                    click_x = int(final_x)
                    click_y = int(final_y)
                    
                    # 2.4 执行点击
                    context.tasker.controller.post_click(click_x, click_y)
                    utils.mfaalog.info(f"[Py] 🖱️ (P&C) 点击坐标: ({click_x}, {click_y})")
                    return True
            
            print("[Py] ⚠️ Patch 成功，但没有有效的识别区域(Box)，无法点击。")
            return True

        except Exception as e:
            utils.mfaalog.error(f"[Py] PatchAndClick 异常: {e}")
            return False
        
@AgentServer.custom_action("PatchBatch")
class PatchBatch(CustomAction):
    """
    V2: 批量打补丁
    支持格式:
    {
        "patches": { 
            "NodeA": { "param": "val" },
            "NodeB": { "param": "val" }
        },
        "origins": {
            "NodeA": { "param": "old_val" },
            "NodeB": { "param": "old_val" }
        }
    }
    """
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        global NODE_BACKUPS
        params = parse_json_arg(argv)
        
        # 获取整个补丁字典 { "NodeName": {data}, ... }
        patches_dict = params.get("patches", {})
        origins_dict = params.get("origins", {})

        if not patches_dict:
            utils.mfaalog.warning("[Py] PatchBatch: 未提供 patches 数据")
            return False

        try:
            # 1. 批量登记备份 (仅当账本中不存在时)
            for node_name, origin_data in origins_dict.items():
                if node_name not in NODE_BACKUPS:
                    NODE_BACKUPS[node_name] = origin_data
                    utils.mfaalog.info(f"[Py] 📖 (Batch) 已登记备份: {node_name}")

            # 2. 批量执行魔改
            # override_pipeline 本身就支持 { A:{...}, B:{...} } 格式
            context.override_pipeline(patches_dict)
            
            utils.mfaalog.info(f"[Py] 🔧 (Batch) 已同时修改 {len(patches_dict)} 个节点")
            return True
        except Exception as e:
            utils.mfaalog.error(f"[Py] PatchBatch 失败: {e}")
            return False
        
# PatchByRegex (正则批量覆写 - 增强版)
# ==============================================================================
# 场景：把所有 "Shop_Buy_*" 的节点超时时间都改成 5秒
@AgentServer.custom_action("PatchByRegex")
class PatchByRegex(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        params = parse_json_arg(argv)
        patterns = params.get("pattern")
        
        # --- 参数解析 ---
        # 模式 A: 深度修改 (指定路径 target_path + value)
        target_path = params.get("target_path") 
        deep_value = params.get("value") 
        
        # 模式 B: 简单覆盖 (指定 patch 字典)
        simple_patch = params.get("patch") 
        
        # 校验
        if not patterns:
            utils.mfaalog.error("[Py] PatchByRegex: 缺少 pattern 参数")
            return False
        if not target_path and not simple_patch:
            utils.mfaalog.error("[Py] PatchByRegex: 必须提供 'target_path' (深度模式) 或 'patch' (简单模式)")
            return False

        if isinstance(patterns, str): patterns = [patterns]

        # 1. 确保数据库已加载
        _ensure_cache_loaded()
        if not ALL_NODES_CACHE:
            utils.mfaalog.error("[Py] 节点数据库为空，无法执行正则匹配")
            return False

        # 2. 准备动态变量 (比如 $box)
        current_roi = [0,0,0,0]
        if argv.box and getattr(argv.box, 'w', 0) > 0:
            current_roi = [int(argv.box.x), int(argv.box.y), int(argv.box.w), int(argv.box.h)]
        
        # 预处理替换值
        final_deep_value = deep_value
        if final_deep_value == "$box": final_deep_value = current_roi
        
        # 3. 开始匹配和修改
        override_dict = {}
        matched_count = 0
        
        try:
            for pat in patterns:
                regex = re.compile(pat)
                
                # 遍历内存数据库中的所有节点
                for node_name, original_config in ALL_NODES_CACHE.items():
                    if regex.search(node_name):
                        
                        # --- 分支 A: 深度修改 ---
                        if target_path:
                            # 深拷贝原始配置
                            new_config = copy.deepcopy(original_config)
                            cursor = new_config
                            try:
                                # 走进深层结构
                                for key in target_path[:-1]:
                                    cursor = cursor[key]
                                
                                # 修改目标字段
                                last_key = target_path[-1]
                                cursor[last_key] = final_deep_value
                                
                                override_dict[node_name] = new_config
                                matched_count += 1
                            except Exception:
                                # 结构不匹配，静默跳过
                                continue
                                
                        # --- 分支 B: 简单覆盖 ---
                        elif simple_patch:
                            # 简单模式直接用 simple_patch，不读取原始配置
                            # 这里支持简单的变量替换逻辑(可选)
                            patch_copy = copy.deepcopy(simple_patch)
                            if patch_copy.get("roi") == "$box":
                                patch_copy["roi"] = current_roi
                                
                            override_dict[node_name] = patch_copy
                            matched_count += 1

            # 4. 提交修改
            if override_dict:
                context.override_pipeline(override_dict)
                utils.mfaalog.info(f"[Py] ⚡ [PatchRegex] 命中了 {matched_count} 个节点 -> 已注入 (Deep/Simple)。")
                return True
            else:
                utils.mfaalog.warning(f"[Py] [PatchRegex] 未命中任何节点 或 路径不匹配。")
                return True

        except Exception as e:
            utils.mfaalog.error(f"[Py] PatchByRegex 执行异常: {e}")
            return False