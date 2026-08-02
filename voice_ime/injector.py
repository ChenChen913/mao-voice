"""文本注入：剪贴板 + 模拟 Ctrl+V。成功后才恢复原剪贴板。"""
import logging
import time

import pyperclip
from pynput.keyboard import Controller, Key

_log = logging.getLogger(__name__)


class Injector:
    def __init__(self):
        self.kb = Controller()

    def inject(self, text):
        prev = None
        try:
            try:
                prev = pyperclip.paste()
            except Exception:
                prev = None
            pyperclip.copy(text)
            time.sleep(0.05)
            self.kb.press(Key.ctrl)
            try:
                self.kb.press("v")
                time.sleep(0.05)
            finally:
                self.kb.release("v")
                self.kb.release(Key.ctrl)
            time.sleep(0.25)
        except Exception:
            _log.exception("Injector 注入失败")
            return False
        finally:
            # 尽快恢复原剪贴板，减少覆盖窗口；恢复失败只记录日志，
            # 不改变返回值（文字已成功注入，不应被误报为失败）
            if prev is not None:
                try:
                    pyperclip.copy(prev)
                except Exception:
                    _log.exception("Injector 恢复剪贴板失败")
        return True
