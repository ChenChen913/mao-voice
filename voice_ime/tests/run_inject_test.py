# -*- coding: utf-8 -*-
"""注入测试：等待目标窗口就绪后执行真实注入（跨进程）"""
import os, sys, time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # voice_ime 根
os.chdir(BASE)
sys.path.insert(0, BASE)

from injector import Injector

for _ in range(100):
    if os.path.exists("target_ready.txt"):
        break
    time.sleep(0.1)

TEXT = "你好测试注入PythonJSON"
inj = Injector()
ok = inj.inject(TEXT)
print("inject() 返回:", ok)

for _ in range(50):
    if os.path.exists("result.txt"):
        break
    time.sleep(0.2)

if os.path.exists("result.txt"):
    with open("result.txt", "r", encoding="utf-8") as f:
        got = f.read().strip()
    print("目标窗口收到:", got)
    print("结果:", "PASS - 注入链路完整" if got == TEXT else "FAIL - 内容不一致: " + repr(got))
else:
    print("结果: FAIL - 目标窗口未收到文本")
