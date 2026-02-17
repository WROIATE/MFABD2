import json
import time
import os
import traceback
import numpy as np
from typing import Union, Optional
from PIL import Image

from maa.agent.agent_server import AgentServer
from maa.custom_recognition import CustomRecognition
from maa.context import Context
from maa.define import RectType

from utils import mfaalog

    # """
    # == HSV 形状匹配识别器 (HSV Shape Matching) ==

    # [核心功能]
    # 专用于解决“半透明”、“低饱和度”、“受背景干扰严重”的图标识别问题。
    # 例如：未激活的灰色技能图标、半透明的 UI 按钮、复杂背景上的白色水印。

    # [工作原理]
    # 1. 颜色过滤：将图像从 BGR 转为 HSV 空间，根据设定的阈值提取目标区域。
    # 2. 二值化：将提取出的区域涂黑 (0)，将背景涂白 (255)，生成一张“白底黑形状”的掩膜图。
    # 3. 模板匹配：将这张处理后的掩膜图，交给 MAA 原生的 TemplateMatch 进行形状匹配。

    # [使用前提]
    # 1. 必须准备一张【白底黑形状】的模板图片 (Template)。
    #    ⚠️ 禁止直接使用原图，请开启debug模式，利用生成的图片截取。
    # 2. 需要针对图标在不同背景下的表现，调试出合适的 HSV 阈值。（已制作了辅助开发工具：不要相信识别，请肉眼操刀调整。）
    # 3. 必须要有一个‘工具人’的节点，内部用二值化后的图片做一个普通的识图（可以多图~）。
    #
    ## 总结：此custom负责改图片，然后输出给‘工具人’节点识别后，返回结果到custom。

    # [参数说明 (JSON)]
    # - target_node (str):  必填。指定要运行的内部识别‘工具人’节点名称 (该节点需定义 template, roi 等)。
    # - lower_hsv (list):   必填。[H, S, V] 下限。例如 [0, 0, 120]。
    # - upper_hsv (list):   必填。[H, S, V] 上限。例如 [180, 50, 255]。
    # - debug (bool):       选填。默认为 False。开启后会在运行目录生成 debug_hsv_xxx.png，用于检查二值化效果。

    # [调试建议]
    # 如果识别失败，请先开启 debug: true。这回生成过滤后的全图，方便截取特征。
    # - 如果生成的图是全白的 -> 说明 HSV 范围太窄，图标漏掉了。
    # - 如果生成的图全是噪点 -> 说明 HSV 范围太宽，背景混进来了。
    # - 实践建议，对亮背景和暗背景做两个识别用or合并在一个节点，比纠结一个完美参数容易得多。
    # """
#================================================================
# {
#----------------------------------------------------------------
#        [节点 1] 入口：尝试识别普通半透明状态
#        策略：使用较宽的 HSV 范围，适配大多数情况。
#----------------------------------------------------------------
#     "FindBunny_Translucent": {
#         "recognition": "Custom",
#         "custom_recognition": "HSVShapeMatching",
#         "custom_recognition_param": {
#             "target_node": "FindBunny_Translucent_Core", // 指向核心节点
#             "lower_hsv": [0, 0, 66],   // S=0~28, V=66~255 (只要不鲜艳且不算太黑)
#             "upper_hsv": [180, 28, 255],
#             "debug": true              // 调试开关
#         },
#         "action": "Click",
#         "next": ["Next_Step_Task"],    // 成功 -> 下一步
#         "on_error": ["FindBunny_Translucent_Light"] // 失败 -> 尝试高亮方案
#     },

#----------------------------------------------------------------
#        [节点 2] 备选：尝试识别高亮/过曝状态
#        策略：当图标背景极亮时，饱和度会更低，亮度下限需提高。
#----------------------------------------------------------------
#     "FindBunny_Translucent_Light": {
#         "recognition": "Custom",
#         "custom_recognition": "HSVShapeMatching",
#         "custom_recognition_param": {
#             "target_node": "FindBunny_Translucent_Core",
#             "lower_hsv": [0, 0, 100],  // V提高到100，排除阴影
#             "upper_hsv": [180, 15, 255], // S压到15，只认极白的物体
#             "debug": true
#         },
#         "action": "Click",
#         "next": ["Next_Step_Task"],    // 成功 -> 下一步
#         "on_error": ["Skip_Or_DeepCheck"] // 都失败 -> 跳过或去深层复查
#     },

#----------------------------------------------------------------
#        [节点 3] 核心定义：模板与区域
#        注意：这个节点通常不直接作为 Task 运行，而是被上面两个节点调用。
#----------------------------------------------------------------
#     "FindBunny_Translucent_Core": {
#         "recognition": "TemplateMatch",
#         "template": "Binary/Binary_skill3_Nol.png", // ⚠️ 必须是白底黑图！
#         "threshold": 0.6,
#         "roi": [ 966, 436, 81, 80 ], // 限制区域，提高效率
#         "green_mask": true // 忽略绿色部分（如果有需要）
#     }
# }
#================================================================


@AgentServer.custom_recognition("HSVShapeMatching")
class HSVShapeMatching(CustomRecognition):
    def analyze(
        self,
        context: Context,
        argv: CustomRecognition.AnalyzeArg,
    ) -> Union[CustomRecognition.AnalyzeResult, Optional[RectType]]:
        """
        [Pillow 兼容版] HSV 形状匹配识别器
        
        特性：
        1. 零依赖：移除 OpenCV 依赖，兼容 Windows ARM64。
        2. 无感迁移：JSON 配置保持 OpenCV 标准 (H:0-180, S:0-255, V:0-255)。
           代码内部自动映射到 Pillow 标准 (H:0-255)。
        """
        try:
            # 1. 解析参数
            raw = argv.custom_recognition_param
            if isinstance(raw, dict):
                params = raw
            else:
                params = json.loads(str(raw))
            
            recognition_node = params.get("target_node") or params.get("recognition")
            debug_mode = params.get("debug", False)
            
            if not recognition_node:
                mfaalog.error("[HSVShapeMatching] 参数错误: 未找到 'target_node'")
                return None

            # img 是 BGR 格式的 Numpy 数组
            img_bgr = argv.image 
            
            # 2. 预处理：BGR -> RGB
            # -------------------------------------------------
            # OpenCV 图片是 BGR，Pillow 需要 RGB。
            # 使用 numpy 切片反转通道，速度极快。
            img_rgb = img_bgr[..., ::-1]

            # Numpy -> PIL Image
            pil_img = Image.fromarray(img_rgb)
            
            # 转 HSV (Pillow 标准: H:0-255, S:0-255, V:0-255)
            hsv_pil = pil_img.convert("HSV")
            hsv_np = np.array(hsv_pil)

            # 3. 核心逻辑：阈值映射与过滤
            # -------------------------------------------------
            # 获取用户配置的 OpenCV 标准阈值 (H: 0-180)
            user_lower = params.get("lower_hsv", [0, 0, 120])
            user_upper = params.get("upper_hsv", [180, 50, 255])

            # --- [关键算法：坐标系映射] ---
            # 目的：将用户输入的 0-180 映射到 PIL 的 0-255
            # 策略：Min向下取整，Max向上取整，确保范围只大不小
            
            def map_h_opencv_to_pillow(h_opencv, is_upper_bound=False):
                # 转换系数
                ratio = 255.0 / 180.0
                val = h_opencv * ratio
                if is_upper_bound:
                    # 上限：向上取整 (Ceil)，防止浮点误差切掉边缘
                    return min(255, int(np.ceil(val)))
                else:
                    # 下限：向下取整 (Floor)
                    return max(0, int(np.floor(val)))

            # 构建 PIL 标准的阈值数组
            # H 通道做映射，S/V 通道保持不变 (两者都是 0-255)
            lower_hsv_pil = np.array([
                map_h_opencv_to_pillow(user_lower[0], is_upper_bound=False),
                user_lower[1],
                user_lower[2]
            ])
            
            upper_hsv_pil = np.array([
                map_h_opencv_to_pillow(user_upper[0], is_upper_bound=True),
                user_upper[1],
                user_upper[2]
            ])

            # 生成掩码 (利用 Numpy 广播机制)
            # 逻辑：(Pixel >= Lower) AND (Pixel <= Upper)
            mask = np.all((hsv_np >= lower_hsv_pil) & (hsv_np <= upper_hsv_pil), axis=-1)
            
            # 4. 二值化与输出构建
            # -------------------------------------------------
            # 创建全白底图 (注意：输出需要 BGR 格式给 MAA，所以直接用 shape 即可)
            # 这里我们直接创建一个和原图一样大小的白色 BGR 图片
            processed_bgr = np.full_like(img_bgr, 255)
            
            # 将掩码区域（目标）涂黑 [0, 0, 0]
            processed_bgr[mask] = [0, 0, 0]

            # 5. 调试输出
            # -------------------------------------------------
            if debug_mode:
                debug_dir = "debug_images"
                if not os.path.exists(debug_dir):
                     try: os.makedirs(debug_dir, exist_ok=True)  
                     except OSError as e: 
                      mfaalog.debug(f"[HSVShapeMatching] 创建调试目录失败: {e}")

                timestamp = f"{time.time():.3f}".replace('.', '_')
                safe_node_name = recognition_node.replace('/', '_').replace('\\', '_')
                
                # 在文件名里标记这是 PIL 处理的，方便区分
                filename = f"{debug_dir}/debug_pil_{safe_node_name}_{timestamp}.png"
                
                # 保存调试图
                # 注意：processed_bgr 是 BGR 格式，保存前要转回 RGB 给 PIL 存
                # 或者如果你有 cv2 可以用 cv2.imwrite，但在无 cv2 环境下必须用 PIL
                debug_save_img = Image.fromarray(processed_bgr[..., ::-1])
                debug_save_img.save(filename)
                
                mfaalog.info(f"[HSVShapeMatching] 调试图已保存: {filename} (H范围: {lower_hsv_pil[0]}~{upper_hsv_pil[0]})")

            # 6. 移交识别
            # -------------------------------------------------
            # 这里的 processed_bgr 已经是标准的 BGR numpy 数组
            # 且已经是【白底黑图】，完全符合 Core 节点的预期
            reco_detail = context.run_recognition(recognition_node, processed_bgr)

            if reco_detail and reco_detail.hit:
                if reco_detail.best_result:
                     mfaalog.debug(f"[HSVShapeMatching] 命中目标: {recognition_node}")
                return CustomRecognition.AnalyzeResult(
                    box=reco_detail.box,
                    detail=reco_detail.raw_detail
                )
            
            return None

        except Exception as e:
            # 打印堆栈以便排查
            mfaalog.error(f"[HSVShapeMatching] 执行异常:\n{traceback.format_exc()}")
            return None