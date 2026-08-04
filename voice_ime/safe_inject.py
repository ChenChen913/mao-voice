"""
安全的剪贴板注入模块  (safe_inject.py)

相比 ../injector.py 的改进：
  1. 使用 GetClipboardSequenceNumber 监控剪贴板是否在操作期间被外部修改
  2. 注入前完整保存所有剪贴板格式（文本、位图、文件列表等），粘贴后尽力恢复
  3. 将"覆盖用户剪贴板"的窗口期从 ~300ms 压缩到 < 50ms
  4. 检测前台窗口是否以管理员权限运行，提前预警 UIPI 拦截而非静默失败
  5. 原剪贴板为非文本时不破坏，恢复失败时明确报告原因

依赖：pynput, ctypes (均为 Windows 原生可用)
平台：纯 Windows / Python 3.13
"""

import ctypes
import ctypes.wintypes as wintypes
import sys
import time

from pynput.keyboard import Controller as KeyboardController
from pynput.keyboard import Key

# ============================================================================
# Windows API 常量
# ============================================================================

# -- 标准剪贴板格式 (Clipboard Formats) --
CF_TEXT = 1             # ANSI 文本
CF_BITMAP = 2           # GDI 位图句柄 (HBITMAP)
CF_DIB = 8              # 设备无关位图 (全局内存块)
CF_UNICODETEXT = 13     # Unicode 文本 (UTF‑16 LE)，最常用的文本格式
CF_HDROP = 15           # 文件/目录列表
CF_DIBV5 = 17           # DIB Version 5 (带色彩空间信息)

# 所有已知格式，用于遍历检测时分类
_TEXT_FORMATS = {CF_UNICODETEXT, CF_TEXT}
_BITMAP_FORMATS = {CF_BITMAP, CF_DIB, CF_DIBV5}
_FILE_FORMATS = {CF_HDROP}

# v5.16（M2）：Ctrl+V 后到恢复剪贴板之间的等待秒数。
# 原固定 25ms 太短：慢应用（Electron/远程桌面/大型 IDE）尚未读取剪贴板时内容已被换回，
# 导致实际粘贴失败却返回成功。默认 200ms，可在配置 inject.restore_delay_sec 调整。
DEFAULT_RESTORE_DELAY_SEC = 0.2

# -- GlobalAlloc 参数 --
GMEM_MOVEABLE = 0x0002      # 可移动全局内存
GMEM_ZEROINIT = 0x0040      # 分配时清零

# -- 进程/令牌访问权限 --
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TOKEN_QUERY = 0x0008

# TokenInformationClass 枚举值
TokenElevationType = 18

# TokenElevationType 返回值
TokenElevationTypeDefault = 1   # 默认 UAC 级别
TokenElevationTypeFull = 2      # 完全提权（管理员运行）
TokenElevationTypeLimited = 3   # 受限令牌（UAC 下普通用户）

# -- 错误码 --
ERROR_ACCESS_DENIED = 5

# -- 复制图像标志 --
IMAGE_BITMAP = 0
LR_COPYRETURNORG = 0x00000004   # CopyImage 返回原始句柄的副本

# ============================================================================
# Windows API 函数注册
# ============================================================================

# --- kernel32 ---
kernel32 = ctypes.windll.kernel32

kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL

kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalFree.restype = wintypes.HGLOBAL

kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = wintypes.LPVOID

kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalUnlock.restype = wintypes.BOOL

kernel32.GlobalSize.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalSize.restype = ctypes.c_size_t

kernel32.GetLastError.argtypes = []
kernel32.GetLastError.restype = wintypes.DWORD

kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL

kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE

# --- user32 ---
user32 = ctypes.windll.user32

user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL

user32.CloseClipboard.argtypes = []
user32.CloseClipboard.restype = wintypes.BOOL

user32.EmptyClipboard.argtypes = []
user32.EmptyClipboard.restype = wintypes.BOOL

user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = wintypes.HANDLE

user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE

user32.EnumClipboardFormats.argtypes = [wintypes.UINT]
user32.EnumClipboardFormats.restype = wintypes.UINT

user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
user32.IsClipboardFormatAvailable.restype = wintypes.BOOL

user32.GetClipboardSequenceNumber.argtypes = []
user32.GetClipboardSequenceNumber.restype = wintypes.DWORD

user32.CopyImage.argtypes = [
    wintypes.HANDLE,
    wintypes.UINT,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
]
user32.CopyImage.restype = wintypes.HANDLE

user32.GetForegroundWindow.argtypes = []
user32.GetForegroundWindow.restype = wintypes.HWND

user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD

user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND

GA_ROOT = 2  # GetAncestor: 获取根所有者窗口

# --- advapi32 ---
advapi32 = ctypes.windll.advapi32

advapi32.OpenProcessToken.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.HANDLE),
]
advapi32.OpenProcessToken.restype = wintypes.BOOL

advapi32.GetTokenInformation.argtypes = [
    wintypes.HANDLE,
    wintypes.UINT,  # ctypes.c_int → wintypes.UINT 避免枚举类型参数错误
    wintypes.LPVOID,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
]
advapi32.GetTokenInformation.restype = wintypes.BOOL

# --- gdi32 ---
gdi32 = ctypes.windll.gdi32

gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteObject.restype = wintypes.BOOL

# --- shell32 ---
shell32 = ctypes.windll.shell32

shell32.DragQueryFileW.argtypes = [
    wintypes.HANDLE,
    wintypes.UINT,
    wintypes.LPWSTR,
    wintypes.UINT,
]
shell32.DragQueryFileW.restype = wintypes.UINT


# ============================================================================
# 内部工具函数
# ============================================================================

def _format_name(fmt: int) -> str:
    """返回剪贴板格式的可读名称，用于日志/错误消息。"""
    names = {
        CF_TEXT: "CF_TEXT(ANSI文本)",
        CF_BITMAP: "CF_BITMAP(位图句柄)",
        CF_DIB: "CF_DIB(设备无关位图)",
        CF_UNICODETEXT: "CF_UNICODETEXT(Unicode文本)",
        CF_HDROP: "CF_HDROP(文件列表)",
        CF_DIBV5: "CF_DIBV5(DIBv5)",
    }
    return names.get(fmt, f"format_id={fmt}")


def _open_clipboard(hwnd_owner: wintypes.HWND | None = None) -> bool:
    """
    打开剪贴板，最多重试 5 次（每次间隔 10ms）。
    剪贴板是全局互斥资源，其他进程可能正在使用，需要短暂重试。
    """
    for _ in range(5):
        if user32.OpenClipboard(hwnd_owner):
            return True
        time.sleep(0.01)
    return False


def _copy_global_mem_block(hdata: wintypes.HGLOBAL) -> wintypes.HGLOBAL | None:
    """
    复制一个全局内存块（用于 CF_TEXT / CF_UNICODETEXT / CF_DIB / CF_HDROP 等）。
    返回新分配的内存句柄，失败返回 None。
    调用者负责最终释放返回的句柄。
    """
    size = kernel32.GlobalSize(hdata)
    if size == 0:
        return None

    new_handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
    if not new_handle:
        return None

    src = kernel32.GlobalLock(hdata)
    if not src:
        # 无法锁定源内存：new_handle 仍归我们，必须释放避免泄漏
        kernel32.GlobalFree(new_handle)
        return None
    dst = kernel32.GlobalLock(new_handle)
    if not dst:
        # 新句柄锁定失败：先解锁源，再释放新句柄
        kernel32.GlobalUnlock(hdata)
        kernel32.GlobalFree(new_handle)
        return None
    ctypes.memmove(dst, src, size)
    kernel32.GlobalUnlock(hdata)
    kernel32.GlobalUnlock(new_handle)
    return new_handle


def _copy_bitmap_handle(hbitmap: wintypes.HANDLE) -> wintypes.HANDLE | None:
    """
    复制 GDI 位图句柄（CF_BITMAP 格式专用）。
    CopyImage 创建位图的独立副本，不依赖原句柄。
    """
    new_handle = user32.CopyImage(
        hbitmap, IMAGE_BITMAP, 0, 0, LR_COPYRETURNORG
    )
    return new_handle if new_handle else None


def _free_saved_clipboard(
    saved: list[tuple[int, wintypes.HANDLE]],
) -> None:
    """
    释放已保存的剪贴板数据。
    - 全局内存句柄 → GlobalFree
    - GDI 位图句柄 → DeleteObject
    """
    for fmt, handle in saved:
        if fmt == CF_BITMAP:
            gdi32.DeleteObject(handle)
        else:
            kernel32.GlobalFree(handle)


def _put_back_saved(saved: list[tuple[int, wintypes.HANDLE]]) -> None:
    """把已保存的剪贴板格式放回当前已打开的剪贴板（v5.11）。

    用于"EmptyClipboard 已清空原剪贴板、但后续设置失败"的错误路径：
    必须把备份格式放回去，否则用户原始剪贴板数据永久丢失。
    SetClipboardData 成功的句柄所有权转给系统，失败的释放。
    """
    remaining = []
    for fmt, handle in saved:
        if not user32.SetClipboardData(fmt, handle):
            remaining.append((fmt, handle))
    for fmt, handle in remaining:
        if fmt == CF_BITMAP:
            gdi32.DeleteObject(handle)
        else:
            kernel32.GlobalFree(handle)
    saved.clear()


def _save_all_clipboard_formats() -> tuple[
    int, list[tuple[int, wintypes.HANDLE]] | None
]:
    """
    枚举并保存当前剪贴板中的所有格式及其数据。
    返回 (打开剪贴板时的序列号, [(格式ID, 数据句柄), ...])。
    如果剪贴板为空，返回空列表。
    如果剪贴板无法打开，返回 (0, None)。
    """
    if not _open_clipboard():
        return 0, None

    try:
        seq = user32.GetClipboardSequenceNumber()
        saved: list[tuple[int, wintypes.HANDLE]] = []

        fmt: int = 0
        while True:
            fmt = user32.EnumClipboardFormats(fmt)
            if fmt == 0:
                break

            hdata = user32.GetClipboardData(fmt)
            if not hdata:
                continue

            # CF_BITMAP 是 GDI 对象，不能用 GlobalAlloc/GlobalLock 复制
            if fmt == CF_BITMAP:
                copy_handle = _copy_bitmap_handle(hdata)
            else:
                copy_handle = _copy_global_mem_block(hdata)

            if copy_handle:
                saved.append((fmt, copy_handle))

        return seq, saved
    finally:
        user32.CloseClipboard()


def _category_of_formats(
    saved: list[tuple[int, wintypes.HANDLE]],
) -> str:
    """
    将已保存的格式列表归类为人类可读字符串。
    用于错误消息和状态描述。
    """
    categories: set[str] = set()
    for fmt, _ in saved:
        if fmt in _TEXT_FORMATS:
            categories.add("文本")
        elif fmt in _BITMAP_FORMATS:
            categories.add("位图/图像")
        elif fmt in _FILE_FORMATS:
            categories.add("文件列表")
        else:
            categories.add(f"其他({_format_name(fmt)})")
    return "、".join(sorted(categories)) if categories else "(空)"


def _restore_clipboard_from_saved(
    saved: list[tuple[int, wintypes.HANDLE]],
    original_seq: int,
) -> tuple[bool, str]:
    """
    用之前保存的数据恢复剪贴板内容。
    返回 (是否成功, 原因/状态描述)。

    恢复前会通过 GetClipboardSequenceNumber 判断剪贴板是否在注入期间
    被用户或其他进程修改：如果序列号未变，说明剪贴板内容仍是我们设置的文本，
    可以安全恢复；如果变了，说明有外部干预，此时不应盲目空剪贴板，
    避免覆盖用户在此期间的新复制内容。
    """
    if not saved:
        # 原剪贴板为空：直接清空我们设置的文本即可
        if not _open_clipboard():
            return False, "原剪贴板为空，但无法打开剪贴板清除注入文本"
        try:
            current_seq = user32.GetClipboardSequenceNumber()
            # 如果序列号没变（仍等于注入后 set_seq），说明还是我们设的文本，可安全清空
            if current_seq == original_seq:
                user32.EmptyClipboard()
            # 否则用户在此期间做了复制，保持不动更安全
        finally:
            user32.CloseClipboard()
        return True, "原剪贴板为空，已清空注入文本（或保留用户新复制内容）"

    current_seq = user32.GetClipboardSequenceNumber()

    # ---- 关键决策：序列号变了说明有外部修改 ----
    if current_seq != original_seq:
        category = _category_of_formats(saved)
        return False, (
            f"剪贴板恢复已跳过：注入期间剪贴板被外部修改"
            f"（原序列号={original_seq}，当前序列号={current_seq}），"
            f"原内容[{category}]已无法安全恢复"
        )

    # 序列号一致，安全恢复
    if not _open_clipboard():
        category = _category_of_formats(saved)
        return False, (
            f"剪贴板恢复失败：无法重新打开剪贴板以恢复原内容[{category}]"
        )

    try:
        user32.EmptyClipboard()
        for i, (fmt, handle) in enumerate(saved):
            if not user32.SetClipboardData(fmt, handle):
                # SetClipboardData 失败：从当前索引到末尾的句柄（含失败项与未处理项）
                # 仍归我们所有，必须全部释放。
                for f, h in saved[i:]:
                    if f == CF_BITMAP:
                        gdi32.DeleteObject(h)
                    else:
                        kernel32.GlobalFree(h)
                # 关键：成功转移的句柄（0..i-1）所有权已归系统，绝不能释放。
                # 必须把列表清空，否则调用方 _free_saved_clipboard 会对它们 double-free。
                saved.clear()
                return False, (f"剪贴板部分恢复失败: 格式 {_format_name(fmt)} "
                               f"SetClipboardData 失败，未转移句柄已释放")
        # 全部成功：清空 saved 因为句柄所有权已转移给系统，调用方不可再释放
        saved.clear()
        return True, "剪贴板已成功恢复"
    finally:
        user32.CloseClipboard()


def _check_uipi_block() -> tuple[bool, str]:
    """
    检测前台窗口是否以管理员权限运行，提前预警 UIPI 拦截。

    UIPI (User Interface Privilege Isolation)：
    Windows Vista+ 的安全机制，低完整性级别的进程无法向高完整性级别的
    进程窗口发送输入消息（SendInput / keybd_event）。

    如果前台窗口进程是高完整性（管理员运行），而当前进程不是，
    则 pynput 的 Ctrl+V 将被拦截，粘贴会静默失败。

    返回 (is_blocked, reason_description)。
    """
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return False, ""

    # 获取前台窗口的实际根所有者窗口（处理 UWP / 多层窗口嵌套）
    root_hwnd = user32.GetAncestor(hwnd, GA_ROOT)
    if root_hwnd:
        hwnd = root_hwnd

    # 获取窗口所属进程 ID
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return False, ""

    # 打开目标进程
    hproc = kernel32.OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION, wintypes.BOOL(False).value, pid.value
    )
    if not hproc:
        err = kernel32.GetLastError()
        if err == ERROR_ACCESS_DENIED:
            # 无法打开受保护进程 → 大概率是管理员进程，UIPI 可能拦截
            return True, "目标窗口进程受保护（无法获取令牌），可能被 UIPI 拦截"
        return False, ""

    try:
        # 打开进程令牌
        htoken = wintypes.HANDLE()
        if not advapi32.OpenProcessToken(
            hproc, TOKEN_QUERY, ctypes.byref(htoken)
        ):
            return False, ""

        try:
            elev_type = wintypes.DWORD()
            ret_len = wintypes.DWORD()
            if not advapi32.GetTokenInformation(
                htoken,
                TokenElevationType,
                ctypes.byref(elev_type),
                ctypes.sizeof(elev_type),
                ctypes.byref(ret_len),
            ):
                return False, ""

            if elev_type.value == TokenElevationTypeFull:
                return True, (
                    "目标窗口以管理员权限运行（TokenElevationType=Full），"
                    "当前进程为非管理员，Ctrl+V 将被 UIPI 拦截，按键会静默失败"
                )
            return False, ""
        finally:
            kernel32.CloseHandle(htoken)
    finally:
        kernel32.CloseHandle(hproc)


def _foreground_root_hwnd() -> int:
    """返回当前前台根窗口的 HWND；获取失败返回 0（B7）。"""
    try:
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return 0
        root_hwnd = user32.GetAncestor(hwnd, GA_ROOT)
        return int(root_hwnd) if root_hwnd else int(hwnd)
    except Exception:
        return 0


def _put_text_to_clipboard(text: str) -> bool:
    """尽力把文本写入剪贴板（注入中止时的降级，B3）；失败返回 False。"""
    if not _open_clipboard():
        return False
    try:
        user32.EmptyClipboard()
        text_bytes = (text + "\0").encode("utf-16-le")
        htext = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(text_bytes))
        if not htext:
            return False
        ptr = kernel32.GlobalLock(htext)
        if not ptr:
            kernel32.GlobalFree(htext)
            return False
        ctypes.memmove(ptr, text_bytes, len(text_bytes))
        kernel32.GlobalUnlock(htext)
        if not user32.SetClipboardData(CF_UNICODETEXT, htext):
            kernel32.GlobalFree(htext)
            return False
        return True
    finally:
        user32.CloseClipboard()


# ============================================================================
# 公共接口
# ============================================================================

def inject(
    text: str,
    restore_delay_sec: float = DEFAULT_RESTORE_DELAY_SEC,
    expected_hwnd: int = 0,
    require_same_focus: bool = True,
) -> tuple[bool, str]:
    """
    将文本注入当前聚焦窗口（剪贴板 + 模拟 Ctrl+V）。

    安全策略：
      1. 注入前保存原剪贴板的【所有格式】（文本/位图/文件列表等）
      2. 检测 UIPI 拦截风险（目标窗口为管理员权限时提前报错）
      3. 将文本放入剪贴板 → 模拟 Ctrl+V → 立即恢复原剪贴板
      4. 整个过程覆盖窗口约 220ms（设置剪贴板 ~5ms + 按键 ~15ms + 等待粘贴 ~200ms，
         可在 inject.restore_delay_sec 调整，钳制范围 0.05~5s）
      5. 通过序列号检测剪贴板是否在操作期间被外部修改，防止误覆盖用户操作

    参数:
        text: 要注入的文本内容（Unicode 字符串）

    返回:
        (成功标志, 状态/错误描述)
        - (True, ...)  注入成功（剪贴板恢复为次级信息：即使恢复未完成也视为成功，
                       原因在 second 中说明，供调用方记录/排查）
        - (False, ...) 注入失败（未注入到目标输入框），second 为具体原因

    示例:
        >>> inject("你好，世界！")
        (True, "注入成功，剪贴板已恢复")

        >>> inject("")
        (False, "输入文本为空")
    """
    # ---- 输入校验 ----
    if not text:
        return False, "输入文本为空"

    # v5.17（N-m2）：restore_delay_sec 来自用户可编辑配置，必须做类型/范围钳制，
    # 否则手改 config 为非数字时 max(0.0, ...) 会抛 TypeError 使注入整体失败
    try:
        delay = float(restore_delay_sec)
    except (TypeError, ValueError):
        delay = DEFAULT_RESTORE_DELAY_SEC
    delay = min(max(delay, 0.05), 5.0)

    # ---- UIPI 检测 ----
    blocked, reason = _check_uipi_block()
    if blocked:
        # v5.17（B3）：中止时把文本复制到剪贴板，避免用户辛苦说的一段话直接丢失
        if _put_text_to_clipboard(text):
            return False, "UIPI 拦截：{}；文本已复制到剪贴板，请手动粘贴".format(reason)
        return False, f"UIPI 拦截：{reason}"

    # ---- 焦点校验（B7）：录制→转写→润色耗时数秒，用户可能已切换到别的窗口。
    # 若前台窗口已变化，直接取消注入且不碰剪贴板；无法获取前台窗口时放行（fail-open）。
    if require_same_focus and expected_hwnd:
        current_hwnd = _foreground_root_hwnd()
        if current_hwnd and current_hwnd != expected_hwnd:
            if _put_text_to_clipboard(text):
                return False, "前台窗口已切换，已取消注入；文本已复制到剪贴板，请手动粘贴"
            return False, "前台窗口已切换，已取消注入（文本未粘贴）"

    # ---- 步骤 1：保存当前剪贴板所有格式 ----
    original_seq, saved = _save_all_clipboard_formats()
    if saved is None:
        return False, "无法打开剪贴板：被其他进程持续占用（重试 5 次均失败）"

    original_category = _category_of_formats(saved)
    has_non_text = any(
        fmt not in _TEXT_FORMATS for fmt, _ in saved
    )

    # ---- 步骤 2：设置新文本到剪贴板 ----
    if not _open_clipboard():
        _free_saved_clipboard(saved)
        return False, "无法打开剪贴板以设置注入文本"

    try:
        user32.EmptyClipboard()

        # 分配全局内存存放 UTF‑16 LE 字符串（含终止 null）
        text_bytes = (text + "\0").encode("utf-16-le")
        text_size = len(text_bytes)
        htext = kernel32.GlobalAlloc(GMEM_MOVEABLE, text_size)
        if not htext:
            # 剪贴板已被 EmptyClipboard 清空：先放回原内容再失败，防止用户数据丢失
            _put_back_saved(saved)
            return False, "分配剪贴板内存失败，原内容已放回"

        ptr = kernel32.GlobalLock(htext)
        if not ptr:
            # GlobalLock 失败（内存不足等）：句柄仍归我们，需释放并还原已保存内容
            kernel32.GlobalFree(htext)
            _put_back_saved(saved)
            return False, "锁定剪贴板内存失败，原内容已放回"
        ctypes.memmove(ptr, text_bytes, text_size)
        kernel32.GlobalUnlock(htext)

        if not user32.SetClipboardData(CF_UNICODETEXT, htext):
            kernel32.GlobalFree(htext)
            # EmptyClipboard 已清空原剪贴板，必须把保存的内容放回，否则用户数据丢失
            user32.EmptyClipboard()
            _put_back_saved(saved)
            return False, "设置剪贴板数据失败，已尝试还原原内容"

        # 记录设置文本后的序列号，用于恢复阶段比对
        set_seq = user32.GetClipboardSequenceNumber()
    finally:
        user32.CloseClipboard()

    # ---- 步骤 3：模拟 Ctrl+V ----
    try:
        keyboard = KeyboardController()

        # 按 Ctrl 后留 2ms 让系统处理修饰键状态
        keyboard.press(Key.ctrl)
        time.sleep(0.002)

        # 按 V 后保持 15ms，让目标应用有足够时间处理 WM_PASTE
        keyboard.press("v")
        time.sleep(0.015)

        # 释放按键（先 V 后 Ctrl，顺序与按下相反更自然）
        keyboard.release("v")
        time.sleep(0.002)
        keyboard.release(Key.ctrl)

        # 等待目标应用完成粘贴后再恢复剪贴板；慢应用需要更长窗口期（M2）
        time.sleep(delay)
    except Exception as e:
        # 按键模拟异常（极少发生，如 pynput 后端初始化失败）
        # 无论粘贴是否成功，都要尝试恢复剪贴板
        _restore_clipboard_from_saved(saved, set_seq)
        _free_saved_clipboard(saved)
        return False, f"按键模拟失败: {e}"

    # ---- 步骤 4：恢复原剪贴板 ----
    restored, restore_msg = _restore_clipboard_from_saved(saved, set_seq)

    # 释放保存的数据（恢复成功后句柄所有权已转给系统，无需再释放；
    # 恢复失败时这些是备份副本，需要手动释放）
    if not restored:
        _free_saved_clipboard(saved)

    # ---- 构建返回消息 ----
    if restored and restore_msg.startswith("剪贴板已成功恢复"):
        detail = "剪贴板已恢复"
        if has_non_text:
            detail += f"，原内容[{original_category}]完整保留"
        elif original_category != "(空)":
            detail += f"，原文本内容已恢复"
        return True, f"注入成功，{detail}"

    if restored:
        # 恢复了但消息不是标准成功（如原剪贴板为空的情况）
        return True, f"注入成功，{restore_msg}"

    # 注入成功但恢复失败/被跳过 → 仍返回 True（v5.4）：
    # 文字已进入目标输入框，恢复原剪贴板只是"尽力而为"的次级操作；
    # 若把这里当失败上报，会让用户看到"明明成功却报错"的误导提示。
    return (
        True,
        f"注入成功，但剪贴板恢复未完成: {restore_msg}",
    )


# ============================================================================
# 冒烟测试（非单元测试，仅验证基本通路）
# ============================================================================

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # v5.13.6：GBK 控制台兼容
    print("safe_inject 冒烟测试")
    print("=" * 40)

    # 测试 1：空文本
    ok, msg = inject("")
    print(f"[测试1] 空文本 → ok={ok}, msg={msg}")
    assert not ok, "空文本应返回 False"

    # 测试 2：基本注入（请手动确认目标窗口能收到文字）
    test_text = "你好，语音输入法测试！🎤"
    ok, msg = inject(test_text)
    print(f"[测试2] 注入基本中文 → ok={ok}, msg={msg}")
    assert ok, f"注入应成功: {msg}"

    # 测试 3：UIPI 检测信息（仅打印，不断言）
    blocked, reason = _check_uipi_block()
    if blocked:
        print(f"[测试3] UIPI 风险检测 → 已拦截: {reason}")
    else:
        print(f"[测试3] UIPI 风险检测 → 无风险或无法判断")

    print("=" * 40)
    print("冒烟测试完成")
    print("提示：请手动将焦点放在记事本等文本编辑器中运行测试2。")
