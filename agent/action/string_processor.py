import json
import re
from maa.context import Context
from maa.custom_action import CustomAction
from maa.agent.agent_server import AgentServer
from utils import mfaalog

@AgentServer.custom_action("BatchNumericPatch")
class BatchNumericPatch(CustomAction):
    """
    配置外置、支持多种分隔符与连接符、自动去重排序
    支持从 attach 动态获取参数并与默认参数合并
    """
    def run(self, context: Context, argv: CustomAction.RunArg):
        try:
            mfaalog.info("[BatchPatch] Action 开始执行 (Attach合并版)...")

            # ================= 🔧 开发者配置区域 🔧 =================
            
            # 1. [分隔符规则] 用于将长字符串切分成多个部分
            # 这是一个正则表达式。默认包含：中文逗号，英文逗号，分号，竖线，所有空白字符(空格/换行)
            SPLIT_PATTERN = r'[，,;\s|]+'

            # 2. [连接符规则] 用于识别范围 (例如 1~5)
            # 这是一个列表。脚本会按顺序检查 token 中是否包含这些字符。
            RANGE_CONNECTORS = ['~', '～', '-']

            # =======================================================

            # 1. 解析基础参数
            try:
                if not argv.custom_action_param:
                    mfaalog.warning("[BatchPatch] 参数为空，跳过执行")
                    return True
                params = json.loads(argv.custom_action_param)
            except json.JSONDecodeError:
                mfaalog.error(f"[BatchPatch] JSON 格式错误: {argv.custom_action_param}")
                return True

            # 获取通用配置
            prefix = params.get("pre_string", "")
            suffix = params.get("post_string", "")
            patch_content = params.get("patch", {})
            
            # ================= 核心修改：输入源合并逻辑 =================
            
            # A. 获取静态默认值 (来自 custom_action_param)
            static_input = str(params.get("input_string", "")).strip()
            
            # B. 获取动态 attach 值
            dynamic_input = ""
            
            # 必须在 JSON 中配置 "node_name" 才能找到对应的节点对象
            current_node_name = params.get("node_name", "")
            # 默认去 attach 里找 "input_string" 这个 key，也可以在 JSON 里自定义
            target_attach_key = params.get("attach_key", "input_string")

            if current_node_name:
                node_obj = context.get_node_object(current_node_name)
                # 检查节点是否存在，且是否有 attach 数据
                if node_obj and node_obj.attach:
                    # 尝试获取目标 key 的值
                    if target_attach_key in node_obj.attach:
                        val = node_obj.attach[target_attach_key]
                        if val is not None:
                            dynamic_input = str(val).strip()
                            mfaalog.info(f"[BatchPatch] 检测到动态 Attach 输入: '{dynamic_input}' (Key: {target_attach_key})")
            
            # C. 合并输入 (使用逗号连接，后续正则会处理多余的逗号)
            # 逻辑：静态值 + "," + 动态值
            # 效果：
            # Case 1: 静态"1-3", 动态"" -> "1-3," -> 解析为 1,2,3
            # Case 2: 静态"", 动态"5" -> ",5" -> 解析为 5
            # Case 3: 静态"1", 动态"5" -> "1,5" -> 解析为 1,5
            raw_input_str = f"{static_input},{dynamic_input}"

            # =======================================================

            # 2. 空输入处理
            # 检查合并后的字符串是否只包含分隔符
            if not raw_input_str.strip(",; \t\n"):
                mfaalog.debug("[BatchPatch] 合并后无有效输入，跳过执行。")
                return True

            # 3. 拆分与解析 (核心逻辑)
            # 先按分隔符拆分
            tokens = [x for x in re.split(SPLIT_PATTERN, raw_input_str) if x]

            # 使用 set 自动去重
            final_number_set = set()
            
            for token in tokens:
                # 检查这个 token 是否包含任意一个连接符
                matched_connector = None
                for conn in RANGE_CONNECTORS:
                    if conn in token:
                        matched_connector = conn
                        break
                
                if matched_connector:
                    # === 处理范围 (例如 "2~5") ===
                    try:
                        parts = token.split(matched_connector)
                        # 确保只有两个部分，且都不为空
                        if len(parts) == 2 and parts[0].strip() and parts[1].strip():
                            start = int(parts[0].strip())
                            end = int(parts[1].strip())
                            
                            # 智能倒序修正 (5~2 -> 2~5)
                            if start > end:
                                start, end = end, start
                            
                            # 生成范围内的所有数字并加入集合
                            for i in range(start, end + 1):
                                final_number_set.add(i)
                        else:
                            mfaalog.warning(f"[BatchPatch] 范围格式怪异: '{token}'，已跳过")
                    except ValueError:
                        mfaalog.warning(f"[BatchPatch] 范围包含非数字: '{token}'，已跳过")
                else:
                    # === 处理单项 (例如 "8") ===
                    try:
                        # 尝试转为 int 以便后续排序和去重 (如果是纯数字场景)
                        num = int(token)
                        final_number_set.add(num)
                    except ValueError:
                        # 如果包含非数字字符(比如 A, B)，保持原样字符串
                        final_number_set.add(token)

            # 4. 排序与构建
            if not final_number_set:
                mfaalog.warning(f"[BatchPatch] 输入 '{raw_input_str}' 未解析出有效内容。")
                return True

            # 转回列表并排序
            final_item_list = list(final_number_set)
            try:
                final_item_list.sort(key=lambda x: int(x) if isinstance(x, int) or (isinstance(x, str) and x.isdigit()) else str(x))
            except:
                final_item_list.sort(key=str)

            # 5. 执行注入
            override_dict = {}
            target_node_names = []

            for item in final_item_list:
                full_node_name = f"{prefix}{item}{suffix}"
                override_dict[full_node_name] = patch_content
                target_node_names.append(full_node_name)

            if override_dict:
                context.override_pipeline(override_dict)
                
                # 优化的日志显示
                if len(target_node_names) > 10:
                    example_str = f"{target_node_names[0]} ... {target_node_names[-1]}"
                else:
                    example_str = ", ".join(target_node_names)
                
                mfaalog.info(f"[BatchPatch] 解析顺序: {final_item_list}")
                mfaalog.info(f"[BatchPatch] 成功注入 {len(target_node_names)} 个节点: {example_str}")
            
            return True

        except Exception as e:
            mfaalog.error(f"[BatchPatch] 运行时发生异常: {e}")
            import traceback
            traceback.print_exc()
            return True