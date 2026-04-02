"""PC端窗口管理 Custom Action

调整棕色尘埃2 PC客户端窗口为 1280x720 窗口化模式，
以匹配 MaaFramework display_short_side=720 的坐标基准。

仅在 Windows 平台有效，其他平台直接跳过。
"""

import sys
import time
from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context

# 目标客户区尺寸（游戏画面，不含标题栏/边框）
TARGET_WIDTH = 1280
TARGET_HEIGHT = 720

# 游戏窗口类名（Win32 controller 里配置的 class_regex）
WINDOW_CLASS = "UnityWndClass"


def _find_and_resize_window() -> tuple[bool, str]:
    """
    查找游戏窗口并调整客户区到 1280x720。

    Returns:
        (success: bool, message: str)
    """
    if sys.platform != "win32":
        return True, "非Windows平台，跳过窗口调整"

    try:
        import ctypes
        import ctypes.wintypes

        user32 = ctypes.windll.user32

        # 枚举所有顶层窗口，找到类名匹配的游戏窗口
        found_hwnd = ctypes.wintypes.HWND(0)

        def enum_callback(hwnd, lparam):
            nonlocal found_hwnd
            buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, buf, 256)
            if buf.value == WINDOW_CLASS:
                # 确认窗口可见
                if user32.IsWindowVisible(hwnd):
                    found_hwnd = hwnd
                    return False  # 停止枚举
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
        user32.EnumWindows(WNDENUMPROC(enum_callback), 0)

        if not found_hwnd:
            return False, f"未找到类名为 '{WINDOW_CLASS}' 的游戏窗口，请先启动游戏"

        hwnd = found_hwnd

        # 获取窗口标题用于日志
        title_buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, title_buf, 256)
        title = title_buf.value

        # 获取当前窗口矩形（含边框）
        window_rect = ctypes.wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(window_rect))

        # 获取当前客户区矩形
        client_rect = ctypes.wintypes.RECT()
        user32.GetClientRect(hwnd, ctypes.byref(client_rect))

        current_client_w = client_rect.right - client_rect.left
        current_client_h = client_rect.bottom - client_rect.top

        if current_client_w == TARGET_WIDTH and current_client_h == TARGET_HEIGHT:
            return True, f"窗口 '{title}' 已是 {TARGET_WIDTH}x{TARGET_HEIGHT}，无需调整"

        # 计算边框大小 = 窗口总大小 - 客户区大小
        window_w = window_rect.right - window_rect.left
        window_h = window_rect.bottom - window_rect.top
        border_w = window_w - current_client_w
        border_h = window_h - current_client_h

        # 目标窗口总大小 = 目标客户区 + 边框
        target_window_w = TARGET_WIDTH + border_w
        target_window_h = TARGET_HEIGHT + border_h

        # 先确保窗口不是最大化/最小化状态
        SW_RESTORE = 9
        user32.ShowWindow(hwnd, SW_RESTORE)
        time.sleep(0.1)

        # 调整窗口大小，保持当前位置
        SWP_NOMOVE = 0x0002
        SWP_NOZORDER = 0x0004
        SWP_FRAMECHANGED = 0x0020
        flags = SWP_NOMOVE | SWP_NOZORDER | SWP_FRAMECHANGED
        result = user32.SetWindowPos(hwnd, 0, 0, 0, target_window_w, target_window_h, flags)

        if not result:
            err = ctypes.GetLastError()
            return False, f"SetWindowPos 失败，错误码: {err}"

        # 验证调整结果
        time.sleep(0.2)
        user32.GetClientRect(hwnd, ctypes.byref(client_rect))
        actual_w = client_rect.right - client_rect.left
        actual_h = client_rect.bottom - client_rect.top

        if actual_w == TARGET_WIDTH and actual_h == TARGET_HEIGHT:
            return True, f"窗口 '{title}' 已调整为 {TARGET_WIDTH}x{TARGET_HEIGHT}"
        else:
            return False, (
                f"调整后客户区为 {actual_w}x{actual_h}，未达到目标 {TARGET_WIDTH}x{TARGET_HEIGHT}。"
                f"游戏可能锁定了分辨率，请在游戏内设置中手动调整为 FHD(1280x720) 窗口化。"
            )

    except ImportError as e:
        return False, f"缺少依赖: {e}"
    except Exception as e:
        return False, f"调整窗口时发生异常: {e}"


@AgentServer.custom_action("PC_ResizeWindow")
class PC_ResizeWindow(CustomAction):
    """
    调整游戏窗口客户区到 1280x720。

    pipeline 用法:
        {
            "action": "Custom",
            "custom_action": "PC_ResizeWindow"
        }

    成功时继续执行 next，失败时走 on_error。
    """

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        success, message = _find_and_resize_window()
        if success:
            print(f"[PC_ResizeWindow] ✅ {message}")
        else:
            print(f"[PC_ResizeWindow] ❌ {message}")
        return success
