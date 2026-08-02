# -*- coding: utf-8 -*-
"""safe_inject 跨进程注入测试：等待目标窗口就绪后调用 safe_inject.inject"""
import os, sys, time
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE)
sys.path.insert(0, BASE)

import safe_inject

for _ in range(100):
    if os.path.exists("target_ready.txt"):
        break
    time.sleep(0.1)

TEXT = "你好安全注入PythonJSON"
ok, reason = safe_inject.inject(TEXT)
print("inject() 返回:", ok, "| reason:", reason)

for _ in range(50):
    if os.path.exists("result.txt"):
        break
    time.sleep(0.2)

if os.path.exists("result.txt"):
    with open("result.txt", "r", encoding="utf-8") as f:
        got = f.read().strip()
    print("目标窗口收到:", got)
    print("结果:", "PASS - safe_inject 注入链路完整" if got == TEXT else "FAIL - 内容不一致: " + repr(got))
else:
    print("结果: FAIL - 目标窗口未收到文本")
